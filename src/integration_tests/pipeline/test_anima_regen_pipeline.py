"""End-to-end pipeline tests for the daily anima regen tick.

User story:
    As a player, each server day my character's anima pool refills by a
    configured percentage — unless a Soulfray ConditionInstance at stage 2+
    (Tearing onward) is blocking regen, or my character is currently engaged
    in a stakes-bearing activity.

Covers:
    1. Baseline regen — depleted anima + no blocking state → tick restores.
    2. Soulfray stage 2 (Tearing) blocks regen — tick does NOT restore.
    3. Soulfray stage 1 (Fraying) does NOT block regen — tick restores.
    4. CharacterEngagement blocks regen — tick does NOT restore.
    5. Already-full anima is a no-op — tick is idempotent at maximum.

Confirms: AnimaConfig singleton + ConditionStage.properties M2M
(blocks_anima_regen) + CharacterEngagement exclusion + tick scheduler
all integrate correctly end-to-end.
"""

from __future__ import annotations

from django.test import TestCase

from integration_tests.game_content.magic import MagicConfigResult, seed_magic_config


class TestAnimaRegenPipeline(TestCase):
    """Full daily anima regen tick pipeline — all gating paths.

    setUpTestData seeds:
    - Magic config singletons (AnimaConfig with daily_regen_percent=5,
      daily_regen_blocking_property_key="blocks_anima_regen")
    - SoulfrayContent (5 stages; stages 2–5 carry the blocks_anima_regen
      Property) via the idempotent SoulfrayContentFactory() call embedded
      inside seed_magic_config().

    Individual tests create their own characters, depleted CharacterAnima
    rows, and optional ConditionInstances at specific stages so each
    scenario is fully isolated.
    """

    config: MagicConfigResult

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.factories import SoulfrayContentFactory

        cls.config = seed_magic_config()
        # Re-call SoulfrayContentFactory() to get stage objects in local scope.
        # Idempotent — returns the same template/stages already seeded by
        # seed_magic_config().
        cls.soulfray_content = SoulfrayContentFactory()
        cls.soulfray_template = cls.soulfray_content.template
        # stages[0] = Fraying (stage_order=1, threshold=1)  — does NOT block
        # stages[1] = Tearing (stage_order=2, threshold=6)  — BLOCKS
        cls.stages = cls.soulfray_content.stages

    # -----------------------------------------------------------------------
    # Scenario 1: baseline regen
    # -----------------------------------------------------------------------

    def test_baseline_regen_restores_anima(self) -> None:
        """Depleted anima + no blocking conditions → tick restores by daily_regen_percent.

        AnimaConfig.daily_regen_percent=5, maximum=100 → regen floor = 5.
        After tick, current should be 5 (floor((100 * 5) // 100)).
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import CharacterAnimaFactory
        from world.magic.services.anima import anima_regen_tick

        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(character=sheet.character, current=0, maximum=100)

        summary = anima_regen_tick()

        anima.refresh_from_db()
        expected_regen = (100 * 5) // 100  # = 5
        self.assertGreaterEqual(summary.regenerated, 1)
        self.assertEqual(anima.current, expected_regen)

    # -----------------------------------------------------------------------
    # Scenario 2: Soulfray stage 2 (Tearing) blocks regen
    # -----------------------------------------------------------------------

    def test_soulfray_stage_2_blocks_regen(self) -> None:
        """Soulfray at stage 2 (Tearing) carries blocks_anima_regen — tick is a no-op.

        The ConditionInstance has current_stage=stages[1] (Tearing), which is one
        of the stages wired with the blocks_anima_regen Property by SoulfrayContentFactory.
        The tick should see condition_blocked >= 1 and leave anima.current unchanged.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import ConditionInstanceFactory
        from world.magic.factories import CharacterAnimaFactory
        from world.magic.services.anima import anima_regen_tick

        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(character=sheet.character, current=0, maximum=100)

        # Soulfray instance at stage 2 (Tearing) — this stage carries the blocking property.
        tearing_stage = self.stages[1]
        ConditionInstanceFactory(
            target=sheet.character,
            condition=self.soulfray_template,
            current_stage=tearing_stage,
            severity=tearing_stage.severity_threshold,
        )

        summary = anima_regen_tick()

        anima.refresh_from_db()
        self.assertGreaterEqual(summary.condition_blocked, 1)
        self.assertEqual(anima.current, 0)

    # -----------------------------------------------------------------------
    # Scenario 3: Soulfray stage 1 (Fraying) does NOT block regen
    # -----------------------------------------------------------------------

    def test_soulfray_stage_1_does_not_block_regen(self) -> None:
        """Soulfray at stage 1 (Fraying) lacks the blocks_anima_regen property.

        Stage 1 (Fraying) is not wired with the blocking property — only stages 2+
        carry it per spec §8.4. The tick should still regen this character's anima.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import ConditionInstanceFactory
        from world.magic.factories import CharacterAnimaFactory
        from world.magic.services.anima import anima_regen_tick

        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(character=sheet.character, current=0, maximum=100)

        # Stage 1 (Fraying) — does NOT carry the blocking property.
        fraying_stage = self.stages[0]
        ConditionInstanceFactory(
            target=sheet.character,
            condition=self.soulfray_template,
            current_stage=fraying_stage,
            severity=fraying_stage.severity_threshold,
        )

        summary = anima_regen_tick()

        anima.refresh_from_db()
        # Character should be regenerated (stage 1 does not block).
        expected_regen = (100 * 5) // 100  # = 5
        self.assertGreaterEqual(summary.regenerated, 1)
        self.assertEqual(anima.current, expected_regen)

    # -----------------------------------------------------------------------
    # Scenario 4: CharacterEngagement blocks regen
    # -----------------------------------------------------------------------

    def test_engagement_blocks_regen(self) -> None:
        """Active CharacterEngagement prevents the tick from regenerating anima.

        Per spec §5.5: characters currently in a stakes-bearing engagement are
        excluded from the daily regen pass. The tick should see engagement_blocked >= 1
        and leave anima.current unchanged.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import CharacterAnimaFactory
        from world.magic.services.anima import anima_regen_tick
        from world.mechanics.factories import CharacterEngagementFactory

        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(character=sheet.character, current=0, maximum=100)
        CharacterEngagementFactory(character=sheet.character)

        summary = anima_regen_tick()

        anima.refresh_from_db()
        self.assertGreaterEqual(summary.engagement_blocked, 1)
        self.assertEqual(anima.current, 0)

    # -----------------------------------------------------------------------
    # Scenario 5: already-full anima is a no-op
    # -----------------------------------------------------------------------

    def test_already_full_anima_is_noop(self) -> None:
        """Character at maximum anima is excluded from the regen queryset.

        The tick queries CharacterAnima where current < maximum.  A full character
        is not examined at all — no regen, no error, summary.examined count unchanged.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import CharacterAnimaFactory
        from world.magic.services.anima import anima_regen_tick

        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(character=sheet.character, current=100, maximum=100)

        anima_regen_tick()

        anima.refresh_from_db()
        # Full character is not in the queryset, so it doesn't count as "examined".
        self.assertEqual(anima.current, 100)
        # The summary may include other characters from other tests (setUpTestData
        # runs once for the class, but each test method runs in a transaction that
        # is rolled back). This scenario only asserts on anima.current — the count
        # fields reflect the entire tick pass across all characters in the DB.
        # The key invariant is that this character's anima stays at maximum.
