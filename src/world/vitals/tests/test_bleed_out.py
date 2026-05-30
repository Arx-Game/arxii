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

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import (
    BleedingOutConditionFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
)
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import advance_bleed_out


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

    def _make_instance_at_stage1(self):
        """Create a ConditionInstance directly at stage 1 (bypasses PG DISTINCT ON)."""
        return ConditionInstanceFactory(
            target=self.character,
            condition=self.bleed_out,
            current_stage=self.stage1,
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
