"""Tests for check_victory, conclude_battle, and maybe_conclude_on_timer (Task 7).

Key invariant: conclude_battle MUST NOT call complete_story (#1716 deferred).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.battles.constants import (
    DECISIVE_MARGIN,
    DEFAULT_VICTORY_THRESHOLD,
    BattleOutcome,
    BattleSideRole,
)
from world.battles.factories import BattleFactory, BattleSideFactory
from world.battles.services import (
    add_side,
    begin_battle_round,
    check_victory,
    conclude_battle,
    maybe_conclude_on_timer,
)


class CheckVictoryTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Victory Check Battle")
        self.attacker = BattleSideFactory(
            battle=self.battle,
            role=BattleSideRole.ATTACKER,
            victory_threshold=DEFAULT_VICTORY_THRESHOLD,
        )
        self.defender = BattleSideFactory(
            battle=self.battle,
            role=BattleSideRole.DEFENDER,
            victory_threshold=DEFAULT_VICTORY_THRESHOLD,
        )

    def test_no_winner_when_both_below_threshold(self) -> None:
        self.attacker.victory_points = 50
        self.attacker.save()
        self.defender.victory_points = 40
        self.defender.save()

        self.assertIsNone(check_victory(battle=self.battle))

    def test_defender_decisive_when_margin_above_decisive_threshold(self) -> None:
        # Defender at threshold + DECISIVE_MARGIN = decisive win
        self.defender.victory_points = DEFAULT_VICTORY_THRESHOLD + DECISIVE_MARGIN
        self.defender.save()

        outcome = check_victory(battle=self.battle)

        self.assertEqual(outcome, BattleOutcome.DEFENDER_DECISIVE)

    def test_defender_marginal_when_just_at_threshold(self) -> None:
        # Exactly at threshold = marginal (margin = 0 < DECISIVE_MARGIN)
        self.defender.victory_points = DEFAULT_VICTORY_THRESHOLD
        self.defender.save()

        outcome = check_victory(battle=self.battle)

        self.assertEqual(outcome, BattleOutcome.DEFENDER_MARGINAL)

    def test_attacker_decisive_when_margin_above_decisive_threshold(self) -> None:
        self.attacker.victory_points = DEFAULT_VICTORY_THRESHOLD + DECISIVE_MARGIN
        self.attacker.save()

        outcome = check_victory(battle=self.battle)

        self.assertEqual(outcome, BattleOutcome.ATTACKER_DECISIVE)

    def test_attacker_marginal_at_threshold(self) -> None:
        self.attacker.victory_points = DEFAULT_VICTORY_THRESHOLD
        self.attacker.save()

        outcome = check_victory(battle=self.battle)

        self.assertEqual(outcome, BattleOutcome.ATTACKER_MARGINAL)


class ConcludeBattleTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Conclude Battle")

    def test_conclude_sets_outcome_and_concluded_at(self) -> None:
        result = conclude_battle(battle=self.battle, outcome=BattleOutcome.DEFENDER_DECISIVE)

        result.refresh_from_db()
        self.assertEqual(result.outcome, BattleOutcome.DEFENDER_DECISIVE)
        self.assertIsNotNone(result.concluded_at)
        self.assertTrue(result.is_concluded)

    def test_conclude_deactivates_backing_scene(self) -> None:
        conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_MARGINAL)

        self.battle.scene.refresh_from_db()
        self.assertFalse(self.battle.scene.is_active)
        self.assertIsNotNone(self.battle.scene.date_finished)

    def test_conclude_is_idempotent(self) -> None:
        """Calling conclude_battle on an already-concluded battle is a no-op."""
        self.battle.outcome = BattleOutcome.DEFENDER_DECISIVE
        self.battle.save()

        result = conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        result.refresh_from_db()
        # Original outcome preserved
        self.assertEqual(result.outcome, BattleOutcome.DEFENDER_DECISIVE)

    def test_conclude_does_not_call_complete_story(self) -> None:
        """conclude_battle MUST NOT call complete_story (#1716 deferred)."""
        with patch("world.stories.services.completion.complete_story") as mock_cs:
            conclude_battle(battle=self.battle, outcome=BattleOutcome.DEFENDER_MARGINAL)
            mock_cs.assert_not_called()


class MaybeConcludeOnTimerTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Timer Battle")
        self.battle.round_limit = 2
        self.battle.save()
        self.attacker = add_side(
            battle=self.battle,
            role=BattleSideRole.ATTACKER,
            victory_threshold=DEFAULT_VICTORY_THRESHOLD,
        )
        self.defender = add_side(
            battle=self.battle,
            role=BattleSideRole.DEFENDER,
            victory_threshold=DEFAULT_VICTORY_THRESHOLD,
        )

    def _exhaust_rounds(self) -> None:
        """Advance and complete round_limit rounds so timer fires."""
        for _ in range(self.battle.round_limit):
            r = begin_battle_round(battle=self.battle)
            r.status = "completed"
            from django.utils import timezone

            r.completed_at = timezone.now()
            r.save()

    def test_no_conclusion_when_active_round_exists(self) -> None:
        begin_battle_round(battle=self.battle)

        result = maybe_conclude_on_timer(battle=self.battle)

        self.assertIsNone(result)
        self.assertFalse(self.battle.is_concluded)

    def test_no_conclusion_when_rounds_below_limit(self) -> None:
        # Only 1 completed round with limit=2
        r = begin_battle_round(battle=self.battle)
        from django.utils import timezone

        r.status = "completed"
        r.completed_at = timezone.now()
        r.save()

        result = maybe_conclude_on_timer(battle=self.battle)

        self.assertIsNone(result)

    def test_defender_wins_on_timeout_when_neither_meets_threshold(self) -> None:
        self._exhaust_rounds()

        result = maybe_conclude_on_timer(battle=self.battle)

        # Neither side met threshold → defender marginal
        self.assertEqual(result, BattleOutcome.DEFENDER_MARGINAL)
        self.battle.refresh_from_db()
        self.assertTrue(self.battle.is_concluded)

    def test_attacker_wins_when_above_threshold_on_timeout(self) -> None:
        self.attacker.victory_points = DEFAULT_VICTORY_THRESHOLD + DECISIVE_MARGIN
        self.attacker.save()

        self._exhaust_rounds()

        result = maybe_conclude_on_timer(battle=self.battle)

        self.assertEqual(result, BattleOutcome.ATTACKER_DECISIVE)

    def test_no_op_when_already_concluded(self) -> None:
        self.battle.outcome = BattleOutcome.DEFENDER_DECISIVE
        self.battle.save()

        result = maybe_conclude_on_timer(battle=self.battle)

        self.assertIsNone(result)
