"""Tests for Battle conclusion -> story beat auto-wiring (#1785)."""

from __future__ import annotations

from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from evennia.utils.test_resources import EvenniaTestCase

from world.battles.constants import BattleOutcome, BattleParticipantStatus, BattleSideRole
from world.battles.factories import BattleFactory, BattleParticipantFactory, BattleSideFactory
from world.battles.models import BattleOutcomeMapping
from world.battles.services import begin_battle_round, conclude_battle
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import RoundStatus
from world.societies.constants import RenownRisk
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    StakeResolutionColumn,
    StoryScope,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeSceneFactory,
    StakeFactory,
    StakeResolutionFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import StakeOutcome
from world.traits.models import CheckOutcome


class BattleOutcomeMappingModelTests(TestCase):
    """Model-level tests for BattleOutcomeMapping."""

    def test_mapping_unique_per_outcome(self) -> None:
        outcome = CheckOutcome.objects.create(name="Decisive Attacker Win", success_level=6)
        BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.ATTACKER_DECISIVE,
            check_outcome=outcome,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BattleOutcomeMapping.objects.create(
                    outcome=BattleOutcome.ATTACKER_DECISIVE,
                    check_outcome=outcome,
                )

    def test_mapping_allows_null_check_outcome(self) -> None:
        mapping = BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.DEFENDER_MARGINAL,
            check_outcome=None,
        )
        self.assertIsNone(mapping.check_outcome)

    def test_str_representation(self) -> None:
        outcome = CheckOutcome.objects.create(name="Decisive Defeat", success_level=-6)
        mapping = BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.DEFENDER_DECISIVE,
            check_outcome=outcome,
        )
        self.assertIn("Defender", str(mapping))


class ClassifyBattleConclusionOutcomeTests(TestCase):
    """classify_battle_conclusion_outcome: BattleOutcome -> CheckOutcome | None."""

    def test_mapped_outcome_returns_check_outcome(self) -> None:
        from world.battles.beat_wiring import classify_battle_conclusion_outcome

        tier = CheckOutcome.objects.create(name="Decisive Attacker Tier", success_level=6)
        BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.ATTACKER_DECISIVE,
            check_outcome=tier,
        )
        battle = BattleFactory(outcome=BattleOutcome.ATTACKER_DECISIVE)
        self.assertEqual(classify_battle_conclusion_outcome(battle), tier)

    def test_unmapped_outcome_returns_none(self) -> None:
        from world.battles.beat_wiring import classify_battle_conclusion_outcome

        battle = BattleFactory(outcome=BattleOutcome.DEFENDER_MARGINAL)
        self.assertIsNone(classify_battle_conclusion_outcome(battle))

    def test_null_check_outcome_mapping_returns_none(self) -> None:
        from world.battles.beat_wiring import classify_battle_conclusion_outcome

        BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.DEFENDER_DECISIVE,
            check_outcome=None,
        )
        battle = BattleFactory(outcome=BattleOutcome.DEFENDER_DECISIVE)
        self.assertIsNone(classify_battle_conclusion_outcome(battle))

    def test_unresolved_outcome_raises_value_error(self) -> None:
        from world.battles.beat_wiring import classify_battle_conclusion_outcome

        battle = BattleFactory()  # default outcome=UNRESOLVED
        with self.assertRaises(ValueError):
            classify_battle_conclusion_outcome(battle)


class ActivateStakesForBattleTests(EvenniaTestCase):
    """activate_stakes_for_battle: locks staked beats linked to battle.scene."""

    def test_no_participants_noops(self) -> None:
        from world.battles.beat_wiring import activate_stakes_for_battle

        battle = BattleFactory()
        activate_stakes_for_battle(battle)  # must not raise

    def test_no_staked_beats_noops(self) -> None:
        from world.battles.beat_wiring import activate_stakes_for_battle

        battle = BattleFactory()
        side = BattleSideFactory(battle=battle, role=BattleSideRole.ATTACKER)
        BattleParticipantFactory(battle=battle, side=side, status=BattleParticipantStatus.ACTIVE)
        activate_stakes_for_battle(battle)  # no EpisodeScene link at all -> no-op

    def test_activates_with_scale_by_party_level_false(self) -> None:
        from world.battles.beat_wiring import activate_stakes_for_battle
        from world.stories.services.stakes import get_open_activation

        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
            risk=RenownRisk.HIGH,
        )
        battle = BattleFactory()
        side = BattleSideFactory(battle=battle, role=BattleSideRole.ATTACKER)
        BattleParticipantFactory(
            battle=battle,
            side=side,
            character_sheet=sheet,
            status=BattleParticipantStatus.ACTIVE,
        )
        EpisodeSceneFactory(episode=episode, scene=battle.scene)

        activate_stakes_for_battle(battle)

        activation = get_open_activation(beat)
        self.assertIsNotNone(activation)
        # Unready (no stakes authored) -> NONE regardless of scale_by_party_level;
        # this test only confirms the wiring calls through and creates a row.
        # Readiness/effective-risk math itself is Task 1's responsibility, already
        # tested there — this asserts the call happened, not the risk math.


class BeginBattleRoundActivatesStakesTests(TestCase):
    """begin_battle_round calls activate_stakes_for_battle exactly once, at round 1."""

    def test_first_round_calls_activate_stakes_for_battle(self) -> None:
        battle = BattleFactory()
        with patch("world.battles.services.activate_stakes_for_battle") as mock_activate:
            begin_battle_round(battle=battle)
        mock_activate.assert_called_once_with(battle)

    def test_second_round_does_not_reactivate(self) -> None:
        battle = BattleFactory()
        with patch("world.battles.services.activate_stakes_for_battle") as mock_activate:
            begin_battle_round(battle=battle)  # round 1
            first_round = battle.current_round
            first_round.status = RoundStatus.COMPLETED
            first_round.save()
            begin_battle_round(battle=battle)  # round 2
        mock_activate.assert_called_once_with(battle)

    def test_first_round_with_no_participants_does_not_raise(self) -> None:
        battle = BattleFactory()
        begin_battle_round(battle=battle)  # real call, no mock — must not raise


class ConcludeBattleResolvesBeatsTests(EvenniaTestCase):
    """Integration: conclude_battle resolves any linked OUTCOME_TIER beat (#1785)."""

    def test_decisive_victory_resolves_linked_beat(self) -> None:
        tier = CheckOutcome.objects.create(name="Battle Victory Wire", success_level=5)
        BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.ATTACKER_DECISIVE,
            check_outcome=tier,
        )
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        StoryProgressFactory(story=story, character_sheet=sheet)
        battle = BattleFactory()
        EpisodeSceneFactory(episode=episode, scene=battle.scene)

        conclude_battle(battle=battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_no_mapping_row_resolves_pending_gm_review(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        StoryProgressFactory(story=story, character_sheet=sheet)
        battle = BattleFactory()
        EpisodeSceneFactory(episode=episode, scene=battle.scene)

        conclude_battle(battle=battle, outcome=BattleOutcome.DEFENDER_MARGINAL)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.PENDING_GM_REVIEW)

    def test_no_linked_beat_noops(self) -> None:
        battle = BattleFactory()
        # No EpisodeScene linking battle.scene to any beat — must not raise.
        conclude_battle(battle=battle, outcome=BattleOutcome.ATTACKER_MARGINAL)
        battle.refresh_from_db()
        self.assertTrue(battle.is_concluded)

    def test_resolves_a_stake_to_win_column(self) -> None:
        tier = CheckOutcome.objects.create(name="Battle Victory Stake Wire", success_level=5)
        BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.DEFENDER_DECISIVE,
            check_outcome=tier,
        )
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        stake = StakeFactory(beat=beat)
        win_branch = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        StoryProgressFactory(story=story, character_sheet=sheet)
        battle = BattleFactory()
        EpisodeSceneFactory(episode=episode, scene=battle.scene)

        conclude_battle(battle=battle, outcome=BattleOutcome.DEFENDER_DECISIVE)

        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.WIN)
        self.assertEqual(outcome.resolution_id, win_branch.pk)
