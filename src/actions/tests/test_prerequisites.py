"""Tests for action prerequisite classes."""

from django.test import TestCase

from actions.prerequisites import MinimumGMLevelPrerequisite, PendingRitualEffectPrerequisite
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.magic.constants import RitualExecutionKind
from world.magic.factories import CharacterResonanceFactory, RitualFactory
from world.magic.models import PendingRitualEffect
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _gm_actor(level: str, *, db_key: str = "GMActor") -> object:
    """Return a Character with a live roster tenure + GMProfile at ``level``.

    Mirrors ``world/scenes/tests/test_scene_admin_services.py``'s
    ``_create_pc_with_account`` helper -- ``active_account`` requires a real
    ``RosterTenure``, not just ``char.db_account``.
    """
    char = CharacterFactory(db_key=db_key)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    GMProfileFactory(account=account, level=level)
    return char


def _plain_actor(*, db_key: str = "PlainActor", is_staff: bool = False) -> object:
    """Return a Character connected to a plain (non-GM) account."""
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"account_{db_key}", is_staff=is_staff)
    char.db_account = account
    char.save()
    return char


class MinimumGMLevelPrerequisiteTests(TestCase):
    """MinimumGMLevelPrerequisite (#2117) -- staff bypass + GMProfile.level tier compare."""

    def test_staff_bypasses_regardless_of_gm_profile(self) -> None:
        actor = _plain_actor(db_key="StaffBypass", is_staff=True)
        met, reason = MinimumGMLevelPrerequisite(GMLevel.SENIOR).is_met(actor)
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_missing_gm_profile_is_refused_even_at_starting_tier(self) -> None:
        actor = _plain_actor(db_key="NoProfile")
        met, reason = MinimumGMLevelPrerequisite(GMLevel.STARTING).is_met(actor)
        self.assertFalse(met)
        self.assertEqual(reason, "GM trust required.")

    def test_actor_with_no_account_is_refused(self) -> None:
        actor = CharacterFactory(db_key="NoAccount")
        met, reason = MinimumGMLevelPrerequisite(GMLevel.STARTING).is_met(actor)
        self.assertFalse(met)
        self.assertEqual(reason, "GM trust required.")

    def test_gm_at_exact_tier_passes(self) -> None:
        actor = _gm_actor(GMLevel.JUNIOR, db_key="ExactTier")
        met, reason = MinimumGMLevelPrerequisite(GMLevel.JUNIOR).is_met(actor)
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_gm_above_tier_passes(self) -> None:
        actor = _gm_actor(GMLevel.SENIOR, db_key="AboveTier")
        met, _reason = MinimumGMLevelPrerequisite(GMLevel.JUNIOR).is_met(actor)
        self.assertTrue(met)

    def test_gm_below_tier_is_refused_with_tier_specific_message(self) -> None:
        actor = _gm_actor(GMLevel.STARTING, db_key="BelowTier")
        met, reason = MinimumGMLevelPrerequisite(GMLevel.JUNIOR).is_met(actor)
        self.assertFalse(met)
        self.assertIn("Junior GM", reason)


class PendingRitualEffectPrerequisiteTests(TestCase):
    def setUp(self):
        self.cr = CharacterResonanceFactory()
        self.sheet = self.cr.character_sheet
        self.character = self.sheet.character
        self.ritual = RitualFactory(
            name="Rite of Weaving",
            execution_kind=RitualExecutionKind.CEREMONY,
            service_function_path="",
        )
        self.prereq = PendingRitualEffectPrerequisite("Rite of Weaving")

    def test_not_met_without_pending_effect(self):
        met, msg = self.prereq.is_met(self.character)
        self.assertFalse(met)
        self.assertIn("Rite of Weaving", msg)

    def test_met_when_pending_effect_exists(self):
        PendingRitualEffect.objects.create(character=self.sheet, ritual=self.ritual)
        met, msg = self.prereq.is_met(self.character)
        self.assertTrue(met)
        self.assertEqual(msg, "")

    def test_not_met_when_ritual_missing(self):
        prereq = PendingRitualEffectPrerequisite("Nonexistent Ritual")
        met, msg = prereq.is_met(self.character)
        self.assertFalse(met)
        self.assertIn("Nonexistent Ritual", msg)
