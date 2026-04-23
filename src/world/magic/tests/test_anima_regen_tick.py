"""Service tests for anima_regen_tick (Scope 6 Phase 9).

Daily scheduler tick that regens anima for characters below max, skipping
engagement-blocked and condition-blocked (blocks_anima_regen property) characters.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.factories import CharacterAnimaFactory
from world.magic.models.anima import AnimaConfig
from world.magic.services.anima import anima_regen_tick
from world.magic.types import AnimaRegenTickSummary
from world.mechanics.factories import BlocksAnimaRegenPropertyFactory, CharacterEngagementFactory


class CharacterAtMaxNotExaminedTests(TestCase):
    """Character at max anima is not examined by the tick."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create the blocking property."""
        BlocksAnimaRegenPropertyFactory()

    def test_character_at_max_not_examined(self) -> None:
        """Character with current == maximum → examined==0."""
        sheet = CharacterSheetFactory()
        CharacterAnimaFactory(
            character=sheet.character,
            current=100,
            maximum=100,
        )

        result = anima_regen_tick()

        self.assertIsInstance(result, AnimaRegenTickSummary)
        self.assertEqual(result.examined, 0)
        self.assertEqual(result.regenerated, 0)
        self.assertEqual(result.engagement_blocked, 0)
        self.assertEqual(result.condition_blocked, 0)


class CharacterBelowMaxNoBlockingConditionsTests(TestCase):
    """Character below max with no blocking conditions gets anima regen applied."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create the blocking property."""
        BlocksAnimaRegenPropertyFactory()

    def test_character_below_max_no_blocking_conditions_regen_applied(self) -> None:
        """Character with current < maximum and no blocking conditions → regen applied."""
        config = AnimaConfig.get_singleton()
        config.daily_regen_percent = 10
        config.save()

        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(
            character=sheet.character,
            current=50,
            maximum=100,
        )

        result = anima_regen_tick()

        self.assertIsInstance(result, AnimaRegenTickSummary)
        self.assertEqual(result.examined, 1)
        self.assertEqual(result.regenerated, 1)
        self.assertEqual(result.engagement_blocked, 0)
        self.assertEqual(result.condition_blocked, 0)

        # Check that anima was updated
        anima.refresh_from_db()
        self.assertEqual(anima.current, 60)


class CharacterBelowMaxSoulfrayStage2SkippedTests(TestCase):
    """Character at Soulfray stage 2+ (blocks_anima_regen property) is skipped."""

    def test_character_below_max_soulfray_stage2_skipped_blocks_anima_regen(
        self,
    ) -> None:
        """Character with Soulfray stage 2 carrying blocks_anima_regen property → skipped."""
        # Create the blocking property
        blocker = BlocksAnimaRegenPropertyFactory()

        # Create Soulfray condition with stages
        soulfray = ConditionTemplateFactory(
            name="Soulfray",
            passive_decay_per_day=0,
        )
        ConditionStageFactory(
            condition=soulfray,
            severity_threshold=10,
            stage_order=1,
        )
        stage2 = ConditionStageFactory(
            condition=soulfray,
            severity_threshold=20,
            stage_order=2,
        )
        # Attach blocker property to stage 2
        stage2.properties.add(blocker)

        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(
            character=sheet.character,
            current=50,
            maximum=100,
        )

        # Create condition instance at stage 2
        ConditionInstanceFactory(
            condition=soulfray,
            target=sheet.character,
            current_stage=stage2,
            severity=15,
        )

        result = anima_regen_tick()

        self.assertIsInstance(result, AnimaRegenTickSummary)
        self.assertEqual(result.examined, 1)
        self.assertEqual(result.regenerated, 0)
        self.assertEqual(result.engagement_blocked, 0)
        self.assertEqual(result.condition_blocked, 1)

        # Check that anima was NOT updated
        anima.refresh_from_db()
        self.assertEqual(anima.current, 50)


class CharacterBelowMaxSoulfrayStage1RegenAppliedTests(TestCase):
    """Character at Soulfray stage 1 (no blocks_anima_regen) gets regen applied."""

    def test_character_below_max_soulfray_stage1_regen_applied(self) -> None:
        """Character with Soulfray stage 1 (no blocking property) → regen applied."""
        config = AnimaConfig.get_singleton()
        config.daily_regen_percent = 10
        config.save()

        # Create the blocking property (exists but NOT attached to stage 1)
        blocker = BlocksAnimaRegenPropertyFactory()

        # Create Soulfray condition with stages
        soulfray = ConditionTemplateFactory(
            name="Soulfray",
            passive_decay_per_day=0,
        )
        stage1 = ConditionStageFactory(
            condition=soulfray,
            severity_threshold=10,
            stage_order=1,
        )
        stage2 = ConditionStageFactory(
            condition=soulfray,
            severity_threshold=20,
            stage_order=2,
        )
        # Attach blocker property only to stage 2, not stage 1
        stage2.properties.add(blocker)

        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(
            character=sheet.character,
            current=50,
            maximum=100,
        )

        # Create condition instance at stage 1
        ConditionInstanceFactory(
            condition=soulfray,
            target=sheet.character,
            current_stage=stage1,
            severity=5,
        )

        result = anima_regen_tick()

        self.assertIsInstance(result, AnimaRegenTickSummary)
        self.assertEqual(result.examined, 1)
        self.assertEqual(result.regenerated, 1)
        self.assertEqual(result.engagement_blocked, 0)
        self.assertEqual(result.condition_blocked, 0)

        # Check that anima was updated
        anima.refresh_from_db()
        self.assertEqual(anima.current, 60)


class CharacterEngagedSkippedTests(TestCase):
    """Character with active CharacterEngagement is skipped."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create the blocking property."""
        BlocksAnimaRegenPropertyFactory()

    def test_engaged_character_skipped(self) -> None:
        """Character with active CharacterEngagement → skipped."""
        config = AnimaConfig.get_singleton()
        config.daily_regen_percent = 10
        config.save()

        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(
            character=sheet.character,
            current=50,
            maximum=100,
        )

        # Create engagement for this character
        CharacterEngagementFactory(character=sheet.character)

        result = anima_regen_tick()

        self.assertIsInstance(result, AnimaRegenTickSummary)
        self.assertEqual(result.examined, 1)
        self.assertEqual(result.regenerated, 0)
        self.assertEqual(result.engagement_blocked, 1)
        self.assertEqual(result.condition_blocked, 0)

        # Check that anima was NOT updated
        anima.refresh_from_db()
        self.assertEqual(anima.current, 50)


class NCharactersSingleDigitQueryCountTests(TestCase):
    """N characters examined in single-digit query count (no N+1)."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create the blocking property."""
        BlocksAnimaRegenPropertyFactory()

    def test_n_characters_single_digit_query_count(self) -> None:
        """Create 10+ CharacterAnima rows → single-digit query count."""
        config = AnimaConfig.get_singleton()
        config.daily_regen_percent = 10
        config.save()

        # Create 10 characters, all below max
        for _ in range(10):
            sheet = CharacterSheetFactory()
            CharacterAnimaFactory(
                character=sheet.character,
                current=50,
                maximum=100,
            )

        # Run with query counting (plan says <=8)
        with self.assertNumQueries(6):
            result = anima_regen_tick()

        self.assertIsInstance(result, AnimaRegenTickSummary)
        self.assertEqual(result.examined, 10)
        self.assertEqual(result.regenerated, 10)
        self.assertEqual(result.engagement_blocked, 0)
        self.assertEqual(result.condition_blocked, 0)
