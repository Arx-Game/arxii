"""Tests for advance_bleed_out staged bleed-out progression service (Task 5 / #595).

Covers:
- Failed resist advances stage; at terminal stage marks character DEAD.
- Passed resist holds stage (no change).
- No Bleeding Out condition → noop, returns False.
- Stage with no resist_check_type is skipped.

SQLite-compatible: ConditionInstances are created directly (not via
apply_condition, which uses a PG-only DISTINCT ON query path).
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
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.mechanics.factories import DeathDeferredPropertyFactory
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory, create_bleed_out_terminal_pool
from world.vitals.services import advance_bleed_out


def _make_npc_source():
    """Return a character with no linked account (NPC source — death-permitting)."""
    return CharacterFactory()


def _make_pc_source():
    """Return a character backed by an AccountDB (PC source — death-forbidden, ADR-0023)."""
    account = AccountFactory()
    character = CharacterFactory()
    character.db_account = account
    character.save(update_fields=["db_account"])
    return character


class AdvanceBleedOutTests(TestCase):
    """Unit tests for advance_bleed_out()."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Character with vitals
        cls.sheet = CharacterSheetFactory()
        cls.vitals = CharacterVitalsFactory(character_sheet=cls.sheet)
        cls.character = cls.sheet.character

        # CheckType used as the resist check
        cls.check_type = CheckTypeFactory()

        # Bleeding-Out condition template with two stages
        cls.bleed_out = BleedingOutConditionFactory()

        # Stage 1 (entry stage, stage_order=1, lower difficulty)
        cls.stage1 = ConditionStageFactory(
            condition=cls.bleed_out,
            stage_order=1,
            name="Bleeding",
            resist_check_type=cls.check_type,
            resist_difficulty=20,
            rounds_to_next=None,
        )
        # Stage 2 (terminal stage, stage_order=2, higher difficulty)
        cls.stage2 = ConditionStageFactory(
            condition=cls.bleed_out,
            stage_order=2,
            name="Dying",
            resist_check_type=cls.check_type,
            resist_difficulty=40,
            rounds_to_next=None,
        )

        # Outcome fixtures used to force check results
        cls.failure_outcome = CheckOutcomeFactory(name="Failure", success_level=-1)
        cls.success_outcome = CheckOutcomeFactory(name="Success", success_level=1)

        # Terminal bleed-out resolution now routes through the bleed_out_terminal
        # consequence pool; seed it so the terminal branch can resolve.
        create_bleed_out_terminal_pool()
        # An NPC source on the dying instance permits death at the terminal stage
        # (death_is_permitted: NPC source, no death_deferral).
        cls.npc_source = _make_npc_source()

    def _make_instance_at_stage1(self):
        """Create a ConditionInstance directly at stage 1 (bypasses PG DISTINCT ON)."""
        return ConditionInstanceFactory(
            target=self.character,
            condition=self.bleed_out,
            current_stage=self.stage1,
            source_character=self.npc_source,
        )

    def _clear_bleed_out(self):
        """Delete any existing Bleeding Out instances for the test character."""
        from world.conditions.models import ConditionInstance

        ConditionInstance.objects.filter(
            target=self.character,
            condition=self.bleed_out,
        ).delete()

    def setUp(self) -> None:
        # Ensure vitals start fresh (ALIVE) and no bleed-out condition
        self.vitals.refresh_from_db()
        self.vitals.life_state = CharacterLifeState.ALIVE
        self.vitals.died_at = None
        self.vitals.save(update_fields=["life_state", "died_at"])
        self._clear_bleed_out()

    def test_failed_resist_advances_then_kills(self) -> None:
        """Two failed resists: first advances to terminal stage, second kills."""
        self._make_instance_at_stage1()

        # First call: fails resist at stage 1 → advance to stage 2 (not yet dead)
        with force_check_outcome(self.failure_outcome):
            died = advance_bleed_out(self.character.sheet_data)
        self.assertFalse(died, "Should not die on first failed resist (stage 1→2)")

        self.vitals.refresh_from_db()
        self.assertEqual(
            self.vitals.life_state,
            CharacterLifeState.ALIVE,
            "Still alive after advancing to terminal stage",
        )

        # Second call: fails resist at stage 2 (terminal) → character dies
        with force_check_outcome(self.failure_outcome):
            died = advance_bleed_out(self.character.sheet_data)
        self.assertTrue(died, "Should die on failed resist at terminal stage")

        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.life_state, CharacterLifeState.DEAD)
        self.assertIsNotNone(self.vitals.died_at)

    def test_passed_resist_holds(self) -> None:
        """Passing the resist check at stage 1 holds the stage — character stays alive."""
        self._make_instance_at_stage1()

        with force_check_outcome(self.success_outcome):
            died = advance_bleed_out(self.character.sheet_data)

        self.assertFalse(died)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.life_state, CharacterLifeState.ALIVE)
        self.assertIsNone(self.vitals.died_at)

    def test_no_bleed_out_condition_noop(self) -> None:
        """Character has no Bleeding Out condition → returns False, stays alive."""
        died = advance_bleed_out(self.character.sheet_data)
        self.assertFalse(died)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.life_state, CharacterLifeState.ALIVE)

    def test_stage_without_resist_check_type_is_skipped(self) -> None:
        """A stage with resist_check_type=None is skipped (no check, no advance)."""
        # Apply condition at stage 1 but clear its resist_check_type
        instance = self._make_instance_at_stage1()
        self.stage1.resist_check_type = None
        self.stage1.save(update_fields=["resist_check_type"])

        try:
            died = advance_bleed_out(self.character.sheet_data)
            self.assertFalse(died)
            self.vitals.refresh_from_db()
            self.assertEqual(self.vitals.life_state, CharacterLifeState.ALIVE)
            # Stage should be unchanged
            instance.refresh_from_db()
            self.assertEqual(instance.current_stage, self.stage1)
        finally:
            # Restore for other tests
            self.stage1.resist_check_type = self.check_type
            self.stage1.save(update_fields=["resist_check_type"])


class AdvanceBleedOutTerminalPoolTests(TestCase):
    """Terminal bleed-out resolves through the gated bleed_out_terminal pool (#1479 T5).

    A single terminal stage (stage_order=1, no higher stage) drives the pool
    resolution: a failed (Failure-tier) roll selects ``die`` only when
    death_is_permitted; otherwise the ``die`` candidate is filtered before
    selection and the victim survives (Bleeding-Out cleared, stays ALIVE).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_type = CheckTypeFactory()
        cls.bleed_out = BleedingOutConditionFactory()
        # Single stage => terminal (no higher stage_order exists).
        cls.terminal_stage = ConditionStageFactory(
            condition=cls.bleed_out,
            stage_order=1,
            name="Dying",
            resist_check_type=cls.check_type,
            resist_difficulty=40,
            rounds_to_next=None,
        )
        # Seed the bleed_out_terminal pool (recover / stay_incapacitated / die).
        cls.pool = create_bleed_out_terminal_pool()
        # The pool's authored outcome tiers (get_or_create by name).
        cls.failure_outcome = CheckOutcomeFactory(name="Failure", success_level=-1)
        cls.success_outcome = CheckOutcomeFactory(name="Success", success_level=1)

    def setUp(self) -> None:
        ConditionInstance.objects.all().delete()

    def _dying_victim(self, *, source_character):
        """Create an ALIVE victim with a terminal Bleeding-Out instance from ``source``."""
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

    def test_npc_source_failed_terminal_can_die(self) -> None:
        """NPC source + Failure roll → death is reachable (life_state becomes DEAD)."""
        sheet = self._dying_victim(source_character=_make_npc_source())

        with force_check_outcome(self.failure_outcome):
            died = advance_bleed_out(sheet)

        self.assertTrue(died, "Death must be reachable for an NPC source")
        sheet.vitals.refresh_from_db()
        self.assertEqual(sheet.vitals.life_state, CharacterLifeState.DEAD)
        self.assertIsNotNone(sheet.vitals.died_at)

    def test_pc_source_failed_terminal_survives(self) -> None:
        """PC source + Failure roll → die filtered; victim survives, Bleeding-Out cleared."""
        sheet = self._dying_victim(source_character=_make_pc_source())

        with force_check_outcome(self.failure_outcome):
            died = advance_bleed_out(sheet)

        self.assertFalse(died, "PvP is non-lethal — death must be filtered (ADR-0023)")
        sheet.vitals.refresh_from_db()
        self.assertEqual(sheet.vitals.life_state, CharacterLifeState.ALIVE)
        self.assertIsNone(sheet.vitals.died_at)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=sheet.character, condition=self.bleed_out
            ).exists(),
            "Bleeding-Out must be cleared once the victim stops dying",
        )

    def test_death_deferred_victim_npc_source_no_death(self) -> None:
        """death_deferred victim + NPC source + Failure roll → no death."""
        sheet = self._dying_victim(source_character=_make_npc_source())
        # Layer an active death_deferred condition onto the victim.
        prop = DeathDeferredPropertyFactory()
        deferred_template = ConditionTemplateFactory()
        deferred_template.properties.add(prop)
        ConditionInstanceFactory(target=sheet.character, condition=deferred_template)

        with force_check_outcome(self.failure_outcome):
            died = advance_bleed_out(sheet)

        self.assertFalse(died, "An active death_deferral blocks death even from an NPC")
        sheet.vitals.refresh_from_db()
        self.assertEqual(sheet.vitals.life_state, CharacterLifeState.ALIVE)

    def test_success_roll_recovers_and_clears_condition(self) -> None:
        """A Success-tier roll selects ``recover`` → condition cleared, victim survives."""
        sheet = self._dying_victim(source_character=_make_npc_source())

        with force_check_outcome(self.success_outcome):
            died = advance_bleed_out(sheet)

        self.assertFalse(died)
        sheet.vitals.refresh_from_db()
        self.assertEqual(sheet.vitals.life_state, CharacterLifeState.ALIVE)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=sheet.character, condition=self.bleed_out
            ).exists(),
        )
