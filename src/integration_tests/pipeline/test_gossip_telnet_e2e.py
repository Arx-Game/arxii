"""Telnet E2E: gossip rumor mill journey (#1572).

Drives ``CmdGossip`` end-to-end through the three gossip verbs (list / plant /
suppress) + seek, asserting DB state after each step and telnet feedback via
``caller.msg``.

Journey layout:
  1. ``gossip``            — list gossipable secrets + their regional heat.
  2. ``gossip plant <#>``  — spread a self-secret → raises regional heat.
  3. ``gossip suppress <#>`` — talk the heat back down.
  4. ``gossip seek``       — overhear a hot secret someone else planted.

Tagged ``@tag("postgres")`` — region resolution walks the ``AreaClosure``
materialized view (PG-only), mirroring ``world.secrets.tests.test_gossip``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase, tag

from commands.social.gossip import CmdGossip
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.roster.factories import RosterEntryFactory
from world.secrets.constants import SecretLevel
from world.secrets.factories import SecretFactory
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.social_checks import seed_social_check_content
from world.skills.factories import CharacterSpecializationValueFactory
from world.skills.models import Specialization
from world.societies.factories import SocietyFactory
from world.traits.factories import CheckOutcomeFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(caller: object, args: str = "") -> CmdGossip:
    """Wire CmdGossip to *caller* and call func(). Returns the cmd instance."""
    cmd = CmdGossip()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"gossip {args}".strip()
    cmd.cmdname = "gossip"
    caller.msg = MagicMock()
    cmd.func()
    return cmd


# ---------------------------------------------------------------------------
# Journey
# ---------------------------------------------------------------------------


@tag("postgres")
class GossipTelnetE2EJourneyTest(TestCase):
    """list → plant → suppress → seek through telnet CmdGossip."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        seed_social_check_content()

        cls.special = CheckOutcomeFactory(name="gossip_special_e2e", success_level=2)
        cls.regular = CheckOutcomeFactory(name="gossip_regular_e2e", success_level=1)

        cls.realm = RealmFactory()
        cls.region = AreaFactory(level=AreaLevel.REGION, realm=cls.realm)
        cls.society = SocietyFactory(realm=cls.realm)

        from evennia_extensions.factories import RoomProfileFactory

        cls.hub = RoomProfileFactory(area=cls.region, is_social_hub=True)

        # Gossiper — has the Gossip specialization (skill gate).
        cls.gossiper_sheet = CharacterSheetFactory()
        cls.gossiper = cls.gossiper_sheet.character
        cls.gossip_spec = Specialization.objects.get(
            name="Gossip", parent_skill__trait__name="Persuasion"
        )
        CharacterSpecializationValueFactory(
            character=cls.gossiper_sheet, specialization=cls.gossip_spec, value=10
        )

        # A self-secret (the gossiper may always spread gossip about themselves).
        cls.secret = SecretFactory(
            subject_sheet=cls.gossiper_sheet, level=SecretLevel.UNCOMMON_KNOWLEDGE
        )

        # Seeker — a second character with Gossip who will overhear the planted secret.
        cls.seeker_sheet = CharacterSheetFactory()
        cls.seeker = cls.seeker_sheet.character
        CharacterSpecializationValueFactory(
            character=cls.seeker_sheet, specialization=cls.gossip_spec, value=10
        )
        cls.seeker_entry = RosterEntryFactory(character_sheet=cls.seeker_sheet)

    def _room(self) -> object:
        return self.hub.objectdb

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    def test_bare_gossip_lists_spreadable_secrets(self) -> None:
        """Bare ``gossip`` lists the character's gossipable secrets."""
        self.gossiper.location = self._room()
        _run(self.gossiper, "")

        msg = self.gossiper.msg.call_args[0][0]
        self.assertIn("Gossip you could spread", msg, "hub should list gossipable secrets")
        self.assertIn(self.secret.content, msg, "self-secret should appear in the list")
        self.assertIn("heat here", msg.lower(), "should show regional heat")

    # ------------------------------------------------------------------
    # plant
    # ------------------------------------------------------------------

    def test_plant_raises_heat(self) -> None:
        """gossip plant <#> → raises the secret's regional heat."""
        from world.secrets.models import SecretGossip

        self.gossiper.location = self._room()
        with force_check_outcome(self.special):
            _run(self.gossiper, "plant 1")

        row = SecretGossip.objects.get(secret=self.secret, region=self.region)
        self.assertEqual(row.heat, 2, "special success should add 2 heat")

        self.gossiper.msg.assert_called()
        msg = self.gossiper.msg.call_args[0][0]
        self.assertIn("spread", msg.lower())
        self.assertIn("heat", msg.lower())

    def test_plant_without_skill_is_rejected(self) -> None:
        """gossip plant by a character without Gossip skill → skill-gate message."""
        from world.character_sheets.factories import CharacterSheetFactory

        bare_sheet = CharacterSheetFactory()
        bare_char = bare_sheet.character
        bare_char.location = self._room()
        _run(bare_char, "plant 1")

        bare_char.msg.assert_called()
        msg = bare_char.msg.call_args[0][0]
        self.assertIn("ear for it", msg.lower())

    # ------------------------------------------------------------------
    # suppress
    # ------------------------------------------------------------------

    def test_suppress_lowers_heat(self) -> None:
        """gossip suppress <#> → lowers the secret's regional heat."""
        from world.secrets.models import SecretGossip

        # Pre-plant: set heat to 5.
        SecretGossip.objects.create(secret=self.secret, region=self.region, heat=5)

        self.gossiper.location = self._room()
        with force_check_outcome(self.special):
            _run(self.gossiper, "suppress 1")

        row = SecretGossip.objects.get(secret=self.secret, region=self.region)
        self.assertEqual(row.heat, 3, "special suppress should remove 2 heat (5 → 3)")

        self.gossiper.msg.assert_called()
        msg = self.gossiper.msg.call_args[0][0]
        self.assertIn("quieted", msg.lower())

    # ------------------------------------------------------------------
    # seek
    # ------------------------------------------------------------------

    def test_seek_surfaces_a_hot_secret(self) -> None:
        """gossip seek → overhears a hot secret planted in the region."""
        from world.secrets.factories import SecretFactory
        from world.secrets.models import SecretGossip, SecretKnowledge

        # A hot secret about a third party that the seeker doesn't know.
        target = CharacterSheetFactory()
        hot = SecretFactory(subject_sheet=target, level=SecretLevel.UNCOMMON_KNOWLEDGE)
        SecretGossip.objects.create(secret=hot, region=self.region, heat=5)

        self.seeker.location = self._room()
        with force_check_outcome(self.regular):
            _run(self.seeker, "seek")

        self.seeker.msg.assert_called()
        msg = self.seeker.msg.call_args[0][0]
        self.assertIn("overhear", msg.lower())
        self.assertIn(hot.content, msg, "should surface the secret's content")

        # The seeker now holds the fact (Level-1 only).
        held = SecretKnowledge.objects.get(roster_entry=self.seeker_entry, secret=hot)
        self.assertFalse(held.knows_category, "seek grants fact only, not deeper layers")
