"""Tests for Battle conclusion -> story beat auto-wiring (#1785, #3559)."""

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
    BeatKind,
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

    def test_check_outcome_is_required(self) -> None:
        """check_outcome is required content now (#3559) - no more null 'pend' row."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BattleOutcomeMapping.objects.create(
                    outcome=BattleOutcome.DEFENDER_MARGINAL,
                    check_outcome=None,
                )

    def test_str_representation(self) -> None:
        outcome = CheckOutcome.objects.create(name="Decisive Defeat", success_level=-6)
        mapping = BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.DEFENDER_DECISIVE,
            check_outcome=outcome,
        )
        self.assertIn("Defender", str(mapping))


class ClassifyBattleConclusionOutcomeTests(TestCase):
    """classify_battle_conclusion_outcome: BattleOutcome -> CheckOutcome."""

    def test_mapped_outcome_returns_check_outcome(self) -> None:
        from world.battles.beat_wiring import classify_battle_conclusion_outcome

        tier = CheckOutcome.objects.create(name="Decisive Attacker Tier", success_level=6)
        BattleOutcomeMapping.objects.create(
            outcome=BattleOutcome.ATTACKER_DECISIVE,
            check_outcome=tier,
        )
        battle = BattleFactory(outcome=BattleOutcome.ATTACKER_DECISIVE)
        self.assertEqual(classify_battle_conclusion_outcome(battle), tier)

    def test_unmapped_outcome_raises(self) -> None:
        """An outcome with no mapping row raises - missing content, not a runtime branch."""
        from world.battles.beat_wiring import classify_battle_conclusion_outcome

        battle = BattleFactory(outcome=BattleOutcome.DEFENDER_MARGINAL)
        with self.assertRaises(BattleOutcomeMapping.DoesNotExist):
            classify_battle_conclusion_outcome(battle)

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
    """Integration: conclude_battle resolves at most one linked beat (#1785, #3559)."""

    def test_linked_battle_grades_its_beat(self) -> None:
        """A battle with an explicitly routed story_beat grades only that beat."""
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
        battle = BattleFactory(story_beat=beat)

        conclude_battle(battle=battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_battle_grades_the_scenes_running_encounter_beat(self) -> None:
        """No explicit story_beat: the battle scene's running beat grades instead,
        but only when it is itself the objective (kind ENCOUNTER, #3559).
        """
        tier = CheckOutcome.objects.create(name="Battle Running Victory", success_level=5)
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
            kind=BeatKind.ENCOUNTER,
        )
        StoryProgressFactory(story=story, character_sheet=sheet)
        battle = BattleFactory()
        battle.scene.running_beat = beat
        battle.scene.save(update_fields=["running_beat"])

        conclude_battle(battle=battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_unlinked_battle_grades_nothing(self) -> None:
        """No story_beat and no running ENCOUNTER beat: an EpisodeScene link alone
        is no longer enough (#3559 replaces the legacy find-all-on-scene scan).
        """
        tier = CheckOutcome.objects.create(name="Battle Unlinked Victory", success_level=5)
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
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_missing_mapping_logs_and_leaves_beat_open(self) -> None:
        """A missing BattleOutcomeMapping row is content, not a pause (#3559): it's
        logged as an error and the beat is left open.
        """
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
        battle = BattleFactory(story_beat=beat)
        # No BattleOutcomeMapping row for DEFENDER_MARGINAL.

        with self.assertLogs("world.battles.beat_wiring", level="ERROR"):
            conclude_battle(battle=battle, outcome=BattleOutcome.DEFENDER_MARGINAL)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_no_linked_beat_noops(self) -> None:
        battle = BattleFactory()
        # No story_beat, no running beat - must not raise.
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
        battle = BattleFactory(story_beat=beat)

        conclude_battle(battle=battle, outcome=BattleOutcome.DEFENDER_DECISIVE)

        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.WIN)
        self.assertEqual(outcome.resolution_id, win_branch.pk)
