"""Telnet E2E for the Ritual of the Durance — witnessed + site-assisted flows (#1700).

Drives the full journey through telnet commands, proving CmdRitual and CmdDurance
wire correctly to the Durance advancement pipeline.

Three test classes:
  WitnessedDuranceTelnetTests — live PC officiant ceremony via CmdRitual:
      draft → join (semi-crossing path declared) → fire → level 3 + path switch.
  SiteDuranceTelnetTests — automated site flow via CmdDurance + CmdRitual:
      status hub → convene → ritual join (auto-fires) → same level-3 outcomes.
  DuranceErrorTelnetTests — error surface:
      no site, unmet requirements, tier-boundary block.

The legend-gate (check_requirements_for_unlock) is patched throughout — it reads a
PG-only materialized view and is tested separately in world.progression.tests (@postgres).
"""

from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone

from commands.durance import CmdDurance
from commands.ritual import CmdRitual
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import (
    CharacterClassFactory,
    CharacterClassLevelFactory,
    PathFactory,
)
from world.classes.models import PathStage
from world.magic.constants import ParticipationRule, TargetKind
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterTraditionFactory,
    GiftFactory,
    ResonanceFactory,
    RitualFactory,
    RitualOfTheDuranceFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterGift, CharacterTechnique, PathGiftGrant, Thread
from world.magic.models.sessions import RitualSession
from world.progression.exceptions import NoDuranceSiteError
from world.progression.factories import DuranceTrainingSiteFactory
from world.progression.models import CharacterPathHistory, ClassLevelAdvancement
from world.progression.models.unlocks import CharacterUnlock, ClassLevelUnlock
from world.progression.selectors import current_path_for_character
from world.progression.services.advancement import _DURANCE_REGISTRATION_SERVICE_PATH
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction
from world.societies.factories import OrganizationFactory

# Patch target: legend-gate called inside advance_class_level_via_session.
# Defined at its module so the lazy import inside the service resolves correctly.
_CHECK = "world.progression.services.spends.check_requirements_for_unlock"

_ORATION = "I have stood in the crucible and I am ready."


# ---------------------------------------------------------------------------
# Command helper (copied verbatim from test_ritual_session_telnet_e2e.py)
# ---------------------------------------------------------------------------


def _run(cmd_cls: type, caller: object, args: str = "") -> object:
    """Build a command instance ready to have .func() called."""
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    return cmd


# ---------------------------------------------------------------------------
# Path / level setup helpers (mirrored from test_durance_e2e.py)
# ---------------------------------------------------------------------------


def _wire_path(sheet, path) -> None:
    """Record *path* as the character's current path via CharacterPathHistory."""
    CharacterPathHistory.objects.create(character=sheet, path=path)


def _set_primary_level(sheet, *, character_class, level: int) -> None:
    """Give sheet.character a primary CharacterClassLevel at *level*."""
    CharacterClassLevelFactory(
        character=sheet,
        character_class=character_class,
        level=level,
        is_primary=True,
    )


# ---------------------------------------------------------------------------
# WitnessedDuranceTelnetTests
# ---------------------------------------------------------------------------


class WitnessedDuranceTelnetTests(TestCase):
    """Live PC officiant ceremony: draft → join (semi-crossing) → fire via CmdRitual.

    Uses setUp (not setUpTestData) to avoid DbHolder deepcopy issues in CI shards.
    """

    def setUp(self) -> None:
        # Shared prospect path — both officiant and inductee on it.
        self.path = PathFactory(stage=PathStage.PROSPECT)

        # Shared room so all characters co-locate (needed for scene scene-witness).
        self.room = ObjectDBFactory()

        # Officiant: real PC at level 10.
        self.officiant = CharacterFactory(db_key="Officiant")
        self.officiant_sheet = CharacterSheetFactory(character=self.officiant)
        officiant_class = CharacterClassFactory()
        _set_primary_level(self.officiant_sheet, character_class=officiant_class, level=10)
        _wire_path(self.officiant_sheet, self.path)
        self.officiant.location = self.room
        self.officiant.save()

        # Inductee: real PC at level 2, will advance to 3.
        self.inductee = CharacterFactory(db_key="Inductee")
        self.inductee_sheet = CharacterSheetFactory(character=self.inductee)
        self.inductee_class = CharacterClassFactory()
        _set_primary_level(self.inductee_sheet, character_class=self.inductee_class, level=2)
        _wire_path(self.inductee_sheet, self.path)
        self.inductee.location = self.room
        self.inductee.save()

        # POTENTIAL child of the prospect path with gift + technique.
        # The level-3 semi-crossing declares this path during the rite.
        self.potential = PathFactory(stage=PathStage.POTENTIAL)
        self.potential.parent_paths.add(self.path)
        self.gift = GiftFactory(name="Pyromancy_witnessed_e2e")
        self.gift.resonances.add(ResonanceFactory(name="Ember_witnessed_e2e"))
        self.tech = TechniqueFactory(name="Flame Lash_witnessed_e2e", gift=self.gift)
        grant = PathGiftGrant.objects.create(path=self.potential, gift=self.gift)
        grant.starter_techniques.add(self.tech)

        # ClassLevelUnlock gate for level 3.
        ClassLevelUnlock.objects.create(
            character_class=self.inductee_class,
            target_level=3,
        )
        CharacterUnlock.objects.create(
            character=self.inductee.sheet_data,
            character_class=self.inductee_class,
            target_level=3,
        )

        # Friend witness: co-located, posts a standard pose so scene_witness_personas
        # picks them up when the receipt is written.
        self.friend = CharacterFactory(db_key="FriendWitness")
        self.friend_sheet = CharacterSheetFactory(character=self.friend)
        self.friend.location = self.room
        self.friend.save()

        # Active scene at the shared room.
        self.scene = SceneFactory(room=self.room, is_active=True)
        Interaction.objects.create(
            scene=self.scene,
            persona=self.friend_sheet.primary_persona,
            content="bears witness",
            pose_kind="standard",
        )

        self.ritual = RitualOfTheDuranceFactory()

    def test_full_witnessed_durance_flow(self) -> None:
        """Witnessed ceremony: draft → join with path + testament → fire → level 3."""
        with mock.patch(_CHECK, return_value=(True, [])):
            # -- Draft --
            cmd = _run(CmdRitual, self.officiant, "draft Ritual of the Durance invite=Inductee")
            cmd.caller.search = MagicMock(return_value=self.inductee)
            cmd.func()
            session_pk = RitualSession.objects.get(ritual=self.ritual).pk

            # -- Join (inductee declares Potential path + testament) --
            cmd = _run(
                CmdRitual,
                self.inductee,
                f"join {session_pk} path={self.potential.name} testament={_ORATION}",
            )
            cmd.func()
            # No site → no auto-fire; session survives.
            self.assertTrue(RitualSession.objects.filter(pk=session_pk).exists())
            self.assertIn("joined", self.inductee.msg.call_args[0][0].lower())

            # -- Fire (officiant completes the rite) --
            cmd = _run(CmdRitual, self.officiant, f"fire {session_pk}")
            cmd.func()

        # Session consumed.
        self.assertFalse(RitualSession.objects.filter(pk=session_pk).exists())

        # Level bumped to 3.
        self.inductee_sheet.invalidate_class_level_cache()
        self.assertEqual(self.inductee_sheet.current_level, 3)

        # Path switched to the chosen Potential path (semi-crossing).
        self.assertEqual(
            current_path_for_character(self.inductee).pk,
            self.potential.pk,
        )

        # Gift, technique, and latent GIFT thread granted.
        self.assertTrue(
            CharacterGift.objects.filter(character=self.inductee_sheet, gift=self.gift).exists()
        )
        self.assertTrue(
            CharacterTechnique.objects.filter(
                character=self.inductee_sheet, technique=self.tech
            ).exists()
        )
        self.assertTrue(
            Thread.objects.filter(
                owner=self.inductee_sheet,
                target_kind=TargetKind.GIFT,
                target_gift=self.gift,
            ).exists()
        )

        # Friend's primary persona recorded as an official witness.
        receipt = ClassLevelAdvancement.objects.get(character_sheet=self.inductee_sheet)
        self.assertIn(self.friend_sheet.primary_persona, receipt.witnesses.all())


# ---------------------------------------------------------------------------
# SiteDuranceTelnetTests
# ---------------------------------------------------------------------------


class SiteDuranceTelnetTests(TestCase):
    """Site-assisted Durance: CmdDurance hub → convene → ritual join (auto-fires)."""

    def setUp(self) -> None:
        # Shared prospect path.
        self.path = PathFactory(stage=PathStage.PROSPECT)

        # Shared room for co-location and site lookup.
        self.room = ObjectDBFactory()

        # Trainer (site officiant): level 10, same path. Does NOT need to be online.
        self.trainer_sheet = CharacterSheetFactory()
        trainer_class = CharacterClassFactory()
        _set_primary_level(self.trainer_sheet, character_class=trainer_class, level=10)
        _wire_path(self.trainer_sheet, self.path)

        # Inductee: level 2, in the room.
        self.inductee = CharacterFactory(db_key="SiteInductee")
        self.inductee_sheet = CharacterSheetFactory(character=self.inductee)
        self.inductee_class = CharacterClassFactory()
        _set_primary_level(self.inductee_sheet, character_class=self.inductee_class, level=2)
        _wire_path(self.inductee_sheet, self.path)
        self.inductee.location = self.room
        self.inductee.save()

        # POTENTIAL child path with gift + technique for the level-3 semi-crossing.
        self.potential = PathFactory(stage=PathStage.POTENTIAL)
        self.potential.parent_paths.add(self.path)
        self.gift = GiftFactory(name="Pyromancy_site_e2e")
        self.gift.resonances.add(ResonanceFactory(name="Ember_site_e2e"))
        self.tech = TechniqueFactory(name="Flame Lash_site_e2e", gift=self.gift)
        grant = PathGiftGrant.objects.create(path=self.potential, gift=self.gift)
        grant.starter_techniques.add(self.tech)

        # ClassLevelUnlock gate for level 3.
        ClassLevelUnlock.objects.create(
            character_class=self.inductee_class,
            target_level=3,
        )
        CharacterUnlock.objects.create(
            character=self.inductee.sheet_data,
            character_class=self.inductee_class,
            target_level=3,
        )

        # Durance training site in the inductee's room, bound to the trainer.
        from world.areas.services import get_room_profile

        room_profile = get_room_profile(self.room)
        DuranceTrainingSiteFactory(room_profile=room_profile, officiant=self.trainer_sheet)

        # Friend witness: co-located, poses into the active scene.
        self.friend = CharacterFactory(db_key="SiteFriendWitness")
        self.friend_sheet = CharacterSheetFactory(character=self.friend)
        self.friend.location = self.room
        self.friend.save()

        # Active scene at the room.
        self.scene = SceneFactory(room=self.room, is_active=True)
        Interaction.objects.create(
            scene=self.scene,
            persona=self.friend_sheet.primary_persona,
            content="observes the Durance",
            pose_kind="standard",
        )

        self.ritual = RitualOfTheDuranceFactory()

    def test_hub_mentions_eligible_path_and_training_site(self) -> None:
        """Bare 'durance' hub shows the eligible Potential path and the training site."""
        with mock.patch(_CHECK, return_value=(True, [])):
            cmd = _run(CmdDurance, self.inductee, "")
            cmd.func()

        output = self.inductee.msg.call_args[0][0]
        self.assertIn(self.potential.name, output)
        self.assertIn("training site is here", output.lower())

    def test_full_site_durance_flow(self) -> None:
        """Convene → join (auto-fires) → level 3, path switched, gift granted, witness recorded."""
        with mock.patch(_CHECK, return_value=(True, [])):
            # -- Convene at the site --
            cmd = _run(CmdDurance, self.inductee, "convene")
            cmd.func()
            output = self.inductee.msg.call_args[0][0]
            self.assertIn("ritual join", output)

            # Resolve session pk from the DB (the convene message embeds it too).
            session_pk = RitualSession.objects.get(ritual=self.ritual).pk

            # -- Join (auto-fires: site trainer has a DuranceTrainingSite) --
            cmd = _run(
                CmdRitual,
                self.inductee,
                f"join {session_pk} path={self.potential.name} testament={_ORATION}",
            )
            cmd.func()

        # Session auto-fired and consumed.
        self.assertFalse(RitualSession.objects.filter(pk=session_pk).exists())

        # Level bumped to 3.
        self.inductee_sheet.invalidate_class_level_cache()
        self.assertEqual(self.inductee_sheet.current_level, 3)

        # Path switched to the chosen Potential path.
        self.assertEqual(
            current_path_for_character(self.inductee).pk,
            self.potential.pk,
        )

        # Gift and technique granted.
        self.assertTrue(
            CharacterGift.objects.filter(character=self.inductee_sheet, gift=self.gift).exists()
        )
        self.assertTrue(
            CharacterTechnique.objects.filter(
                character=self.inductee_sheet, technique=self.tech
            ).exists()
        )
        self.assertTrue(
            Thread.objects.filter(
                owner=self.inductee_sheet,
                target_kind=TargetKind.GIFT,
                target_gift=self.gift,
            ).exists()
        )

        # Friend's primary persona recorded as an official witness.
        receipt = ClassLevelAdvancement.objects.get(character_sheet=self.inductee_sheet)
        self.assertIn(self.friend_sheet.primary_persona, receipt.witnesses.all())


# ---------------------------------------------------------------------------
# DuranceRegistrationTelnetTests
# ---------------------------------------------------------------------------


def _heard(character) -> str:
    """Everything the (mocked) ``character.msg`` was sent, as one string."""
    return " ".join(str(call) for call in character.msg.call_args_list)


class DuranceRegistrationTelnetTests(TestCase):
    """Intake rite through CmdRitual: draft -> join with NO testament -> fire (#4743).

    An empty testament makes the rite compose one from the Glimpse story, and the
    enrollment antiphon is read off the inductee's active tradition. A friend in the
    room hears what the room is told.
    """

    def setUp(self) -> None:
        self.room = ObjectDBFactory()
        self.officiant = CharacterFactory(db_key="IntakeOfficiant")
        CharacterSheetFactory(character=self.officiant)
        self.inductee = CharacterFactory(db_key="IntakeInductee")
        self.inductee_sheet = CharacterSheetFactory(character=self.inductee)
        self.friend = CharacterFactory(db_key="IntakeFriend")
        CharacterSheetFactory(character=self.friend)
        for character in (self.officiant, self.inductee, self.friend):
            character.location = self.room
            character.save()
        self.scene = SceneFactory(room=self.room, is_active=True)
        OrganizationFactory(name="Shroudwatch Academy")
        self.ritual = RitualFactory(
            name="Ritual of the Durance: Registration",
            service_function_path=_DURANCE_REGISTRATION_SERVICE_PATH,
            participation_rule=ParticipationRule.INDUCTION,
            min_participants=2,
        )

    def _register_with_empty_testament(self) -> None:
        cmd = _run(
            CmdRitual,
            self.officiant,
            "draft Ritual of the Durance: Registration invite=IntakeInductee",
        )
        cmd.caller.search = MagicMock(return_value=self.inductee)
        cmd.func()
        session_pk = RitualSession.objects.get(ritual=self.ritual).pk
        _run(CmdRitual, self.inductee, f"join {session_pk}").func()
        self.friend.msg = MagicMock()
        _run(CmdRitual, self.officiant, f"fire {session_pk}").func()
        self.assertFalse(RitualSession.objects.filter(pk=session_pk).exists())
        self.inductee_sheet.refresh_from_db()
        self.assertIsNotNone(self.inductee_sheet.durance_entered_at)

    def _testament(self) -> str:
        return Interaction.objects.get(
            scene=self.scene, persona=self.inductee_sheet.primary_persona
        ).content

    def test_aura_and_active_tradition(self) -> None:
        """The posted testament carries the Glimpse story; the room hears the sponsored key."""
        CharacterAuraFactory(
            character=self.inductee_sheet, glimpse_story="A lamp lit itself in my hands."
        )
        CharacterTraditionFactory(character=self.inductee_sheet)

        self._register_with_empty_testament()

        self.assertEqual(
            self._testament(), "I am IntakeInductee.\n\nA lamp lit itself in my hands."
        )
        self.assertIn("[durance_antiphon_sponsored]", _heard(self.friend))

    def test_no_aura_and_no_tradition(self) -> None:
        """The testament is the name line alone; the room hears the unsponsored key."""
        self._register_with_empty_testament()

        self.assertEqual(self._testament(), "I am IntakeInductee.")
        self.assertIn("[durance_antiphon_unsponsored]", _heard(self.friend))

    def test_ended_and_active_tradition_rows(self) -> None:
        """An ended membership beside the active one neither raises nor decides the key."""
        CharacterTraditionFactory(character=self.inductee_sheet, left_at=timezone.now())
        CharacterTraditionFactory(character=self.inductee_sheet)

        self._register_with_empty_testament()

        self.assertIn("[durance_antiphon_sponsored]", _heard(self.friend))

    def test_only_an_ended_tradition_row(self) -> None:
        """A character whose only membership has ended is unsponsored."""
        CharacterTraditionFactory(character=self.inductee_sheet, left_at=timezone.now())

        self._register_with_empty_testament()

        self.assertIn("[durance_antiphon_unsponsored]", _heard(self.friend))


# ---------------------------------------------------------------------------
# DuranceErrorTelnetTests
# ---------------------------------------------------------------------------


class DuranceErrorTelnetTests(TestCase):
    """Error surface: no site, unmet requirements, tier-boundary block."""

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)
        self.room = ObjectDBFactory()

        self.inductee = CharacterFactory(db_key="ErrorInductee")
        self.inductee_sheet = CharacterSheetFactory(character=self.inductee)
        self.inductee_class = CharacterClassFactory()
        _set_primary_level(self.inductee_sheet, character_class=self.inductee_class, level=2)
        _wire_path(self.inductee_sheet, self.path)
        self.inductee.location = self.room
        self.inductee.save()

        # Unlock needed for requirements check path.
        ClassLevelUnlock.objects.create(
            character_class=self.inductee_class,
            target_level=3,
        )
        CharacterUnlock.objects.create(
            character=self.inductee.sheet_data,
            character_class=self.inductee_class,
            target_level=3,
        )

    def test_convene_no_site_surfaces_no_site_error(self) -> None:
        """No DuranceTrainingSite in the room → NoDuranceSiteError user message."""
        with mock.patch(_CHECK, return_value=(True, [])):
            cmd = _run(CmdDurance, self.inductee, "convene")
            cmd.func()
        output = self.inductee.msg.call_args[0][0]
        self.assertIn(NoDuranceSiteError.user_message, output)

    def test_convene_unmet_requirements_surfaces_reason(self) -> None:
        """Unmet requirements from check_requirements_for_unlock show in the caller message."""
        with mock.patch(_CHECK, return_value=(False, ["Requires 50 Legend"])):
            cmd = _run(CmdDurance, self.inductee, "convene")
            cmd.func()
        output = self.inductee.msg.call_args[0][0]
        self.assertIn("Requires 50 Legend", output)

    def test_convene_at_tier_boundary_surfaces_audere_majora_message(self) -> None:
        """Inductee at a tier-boundary level → convene raises TierBoundaryRequiresCrossing."""
        from world.magic.factories import ensure_audere_majora_threshold

        ensure_audere_majora_threshold(boundary_level=2)

        # No _CHECK patch needed: tier-boundary check fires before check_requirements_for_unlock.
        cmd = _run(CmdDurance, self.inductee, "convene")
        cmd.func()
        output = self.inductee.msg.call_args[0][0]
        # TierBoundaryRequiresCrossing.user_message contains "Audere Majora" and "Crossing".
        self.assertIn("Audere Majora", output)
