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
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.scenes.constants import RoundStatus
from world.societies.constants import RenownRisk
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    StakeResolutionColumn,
    StakeSeverity,
    StoryMaturity,
    StoryScope,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeSceneFactory,
    StakeFactory,
    StakeResolutionFactory,
    StakeRewardLineFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    seed_default_risk_calibrations,
)
from world.stories.models import StakeOutcome, TransitionRequiredOutcome
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

    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_risk_calibrations()

    def _ready_beat(self, episode, risk=RenownRisk.HIGH, target_level=4):
        """A beat that actually clears validate_stakes_readiness, anchored to ``episode``.

        Same shape as ``world.stories.tests.test_services_stakes.ActivationTests
        ._ready_beat``: a DIRE stake (meets HIGH's floor/ceiling) plus a
        downstream OUTLINE beat carrying a REMOVAL stake one failure-hop away
        (HIGH's ceiling sits below REMOVAL's severity, so jeopardy has to be
        reached via the fuse walk), plus a WIN-column reward line inside HIGH's
        band. Built directly on the caller's episode (not a fresh one reassigned
        after the fact) so the failure-hop Transition stays anchored correctly.
        """
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
            risk=risk,
            target_level=target_level,
        )
        stake = StakeFactory(beat=beat, severity=StakeSeverity.DIRE)
        win = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        StakeRewardLineFactory(resolution=win, amount=400)  # in HIGH's reward band (#1770 PR3)
        fight_episode = EpisodeFactory(chapter=episode.chapter, maturity=StoryMaturity.OUTLINE)
        transition = TransitionFactory(source_episode=episode, target_episode=fight_episode)
        TransitionRequiredOutcome.objects.create(
            transition=transition, beat=beat, required_outcome=BeatOutcome.FAILURE
        )
        fight_beat = BeatFactory(episode=fight_episode, risk=RenownRisk.EXTREME)
        removal_stake = StakeFactory(beat=fight_beat, severity=StakeSeverity.REMOVAL)
        StakeResolutionFactory(stake=removal_stake, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=removal_stake, column=StakeResolutionColumn.LOSS)
        return beat

    def _sheets_at_levels(self, *levels):
        """Build CharacterSheet rows whose ``_character_level`` is exactly ``levels``."""
        sheets = []
        for level in levels:
            sheet = CharacterSheetFactory()
            char_class = CharacterClassFactory()
            CharacterClassLevelFactory(character=sheet, character_class=char_class, level=level)
            sheets.append(sheet)
        return sheets

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
        """Real, non-mocked proof: an over-leveled party still prices at declared risk.

        A HIGH-risk ready beat, enlisted party 4 levels over target_level (the
        exact gap that would shift HIGH -> LOW under scale_by_party_level=True,
        per compute_effective_risk / ActivationTests.test_activation_computes_
        effective_risk_for_party). If scale_by_party_level were ever dropped
        from activate_stakes_for_battle's call to activate_stakes_contract,
        effective_risk would come back LOW here instead of HIGH, and this
        test would fail — unlike the previous unready-beat version, which
        could not distinguish True from False (#1785 final review).
        """
        from world.battles.beat_wiring import activate_stakes_for_battle
        from world.stories.services.stakes import get_open_activation

        story = StoryFactory(scope=StoryScope.CHARACTER)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = self._ready_beat(episode)  # HIGH risk, target_level=4

        battle = BattleFactory()
        side = BattleSideFactory(battle=battle, role=BattleSideRole.ATTACKER)
        for sheet in self._sheets_at_levels(8, 8):  # 4 over target -> -2 tiers if scaled
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
        self.assertTrue(activation.is_ready)
        self.assertEqual(activation.declared_risk, RenownRisk.HIGH)
        self.assertEqual(activation.effective_risk, RenownRisk.HIGH)  # not downgraded to LOW


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

    def test_one_battle_applies_same_tier_to_every_linked_beat(self) -> None:
        """One Battle grades as one outcome tier, applied uniformly (#1785 Decision 2).

        Two distinct beats on two different episodes/stories, both linked to
        the same battle's scene, both resolve to the SAME BeatOutcome from a
        single conclude_battle call — per-front independent grading is #1760's
        job, not this wiring's.
        """
        tier = CheckOutcome.objects.create(name="Battle Victory Uniform Tier", success_level=5)
        BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.ATTACKER_DECISIVE,
            check_outcome=tier,
        )
        battle = BattleFactory()

        sheet_a = CharacterSheetFactory()
        story_a = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet_a)
        chapter_a = ChapterFactory(story=story_a)
        episode_a = EpisodeFactory(chapter=chapter_a)
        beat_a = BeatFactory(
            episode=episode_a,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        StoryProgressFactory(story=story_a, character_sheet=sheet_a)
        EpisodeSceneFactory(episode=episode_a, scene=battle.scene)

        sheet_b = CharacterSheetFactory()
        story_b = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet_b)
        chapter_b = ChapterFactory(story=story_b)
        episode_b = EpisodeFactory(chapter=chapter_b)
        beat_b = BeatFactory(
            episode=episode_b,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        StoryProgressFactory(story=story_b, character_sheet=sheet_b)
        EpisodeSceneFactory(episode=episode_b, scene=battle.scene)

        conclude_battle(battle=battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        beat_a.refresh_from_db()
        beat_b.refresh_from_db()
        self.assertEqual(beat_a.outcome, BeatOutcome.SUCCESS)
        self.assertEqual(beat_b.outcome, BeatOutcome.SUCCESS)

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
