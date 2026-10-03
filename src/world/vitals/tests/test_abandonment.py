"""Tests for resolve_abandonment + the shared pool-resolution helper (#1479 Task 8).

``resolve_abandonment`` resolves an abandoned downed victim's fate through the
source-appropriate abandonment pool (``select_abandonment_pool``), reusing the
SAME gated core as the terminal bleed-out path (``_resolve_peril_via_pool``):

- death is reachable only when ``death_is_permitted`` (NPC source, no
  death-deferral); a PC source filters the ``die`` candidate (ADR-0023).
- on survival the acute-peril condition is cleared; on death the single death
  writer (``_mark_dead``) stamps life_state.

SQLite-compatible: the resolution path (select_consequence + apply_resolution +
remove_condition) is the same one ``AdvanceBleedOutTerminalPoolTests`` exercises
on the SQLite fast tier; it does NOT call ``apply_condition`` (the PG-only
DISTINCT ON path), so no postgres tag is needed.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import (
    BleedingOutConditionFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
)
from world.conditions.models import ConditionInstance
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory, create_abandonment_pools
from world.vitals.services import resolve_abandonment


def _make_npc_source():
    """Return a character with no CharacterSheet/roster tenure (NPC source —
    death-permitting)."""
    return CharacterFactory()


def _make_pc_source():
    """Return a character backed by an active RosterTenure (PC source —
    death-forbidden, ADR-0023). db_account is also wired (an "online" PC); the
    canonical PC test is the tenure, not the account (#4091 task 12 fix round 3)
    -- see ``_make_offline_pc_source`` for the test double that distinguishes
    the two."""
    account = AccountFactory()
    character = CharacterFactory()
    character.db_account = account
    character.save(update_fields=["db_account"])
    sheet = CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, end_date=None)
    return character


def _make_offline_pc_source():
    """Return a character backed by an active RosterTenure but NO db_account --
    an offline PC source (#4091 task 12 fix round 3). The regression this
    fixes: an offline PC's attack was previously misread as NPC-sourced and
    could kill, breaking ADR-0023 (PvP is structurally non-lethal) and the
    "AFK never kills" invariant."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, end_date=None)
    return character


class ResolveAbandonmentTests(TestCase):
    """Unit tests for resolve_abandonment()."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_type = CheckTypeFactory()
        cls.bleed_out = BleedingOutConditionFactory()
        cls.terminal_stage = ConditionStageFactory(
            condition=cls.bleed_out,
            stage_order=1,
            name="Dying",
            resist_check_type=cls.check_type,
            resist_difficulty=40,
            rounds_to_next=None,
        )
        create_abandonment_pools()
        cls.failure_outcome = CheckOutcomeFactory(name="Failure", success_level=-1)
        cls.success_outcome = CheckOutcomeFactory(name="Success", success_level=1)

    def setUp(self) -> None:
        ConditionInstance.objects.all().delete()

    def _dying_victim(self, *, source_character):
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(
            character_sheet=sheet,
            life_state=CharacterLifeState.ALIVE,
            health=-5,
            max_health=100,
        )
        ConditionInstanceFactory(
            target=sheet.character,
            condition=self.bleed_out,
            current_stage=self.terminal_stage,
            source_character=source_character,
        )
        return sheet

    def test_npc_source_failed_can_die(self) -> None:
        """NPC source + Failure roll → death reachable via abandonment_enemy pool.

        Regression for #1479 review finding: the acute-peril condition must ALSO be
        cleared on death so _danger_persists returns False and the DANGER round
        auto-ends instead of freezing with a dead victim who still carries bleed-out.
        """
        sheet = self._dying_victim(source_character=_make_npc_source())

        with force_check_outcome(self.failure_outcome):
            died = resolve_abandonment(sheet)

        self.assertTrue(died)
        sheet.vitals.refresh_from_db()
        self.assertEqual(sheet.vitals.life_state, CharacterLifeState.DEAD)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=sheet.character, condition=self.bleed_out
            ).exists(),
            "Bleeding-Out condition must be cleared on death so _danger_persists goes False",
        )

    def test_pc_source_failed_survives(self) -> None:
        """PC source + Failure roll → die filtered (ADR-0023); victim survives, cleared."""
        sheet = self._dying_victim(source_character=_make_pc_source())

        with force_check_outcome(self.failure_outcome):
            died = resolve_abandonment(sheet)

        self.assertFalse(died)
        sheet.vitals.refresh_from_db()
        self.assertEqual(sheet.vitals.life_state, CharacterLifeState.ALIVE)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=sheet.character, condition=self.bleed_out
            ).exists()
        )

    def test_offline_pc_source_failed_survives(self) -> None:
        """#4091 task 12 fix round 3: an OFFLINE PC source (active tenure, no
        db_account) must still filter ``die`` (ADR-0023) -- this is the exact
        "AFK never kills" regression the fix round closes."""
        offline_pc = _make_offline_pc_source()
        self.assertIsNone(offline_pc.db_account)
        sheet = self._dying_victim(source_character=offline_pc)

        with force_check_outcome(self.failure_outcome):
            died = resolve_abandonment(sheet)

        self.assertFalse(died)
        sheet.vitals.refresh_from_db()
        self.assertEqual(sheet.vitals.life_state, CharacterLifeState.ALIVE)

    def test_success_recovers_and_clears(self) -> None:
        """A Success roll selects recover → condition cleared, victim survives."""
        sheet = self._dying_victim(source_character=_make_npc_source())

        with force_check_outcome(self.success_outcome):
            died = resolve_abandonment(sheet)

        self.assertFalse(died)
        sheet.vitals.refresh_from_db()
        self.assertEqual(sheet.vitals.life_state, CharacterLifeState.ALIVE)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=sheet.character, condition=self.bleed_out
            ).exists()
        )

    def test_no_acute_peril_is_noop(self) -> None:
        """Rescue-before-N: the bleed-out is already cleared → no roll, returns False."""
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, life_state=CharacterLifeState.ALIVE)

        died = resolve_abandonment(sheet)

        self.assertFalse(died)
        sheet.vitals.refresh_from_db()
        self.assertEqual(sheet.vitals.life_state, CharacterLifeState.ALIVE)
