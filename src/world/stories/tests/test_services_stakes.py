"""Service tests for the stakes contract engine (#1770 PR1)."""

from django.test import TestCase

from world.societies.constants import RenownRisk
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    StakeResolutionColumn,
    StakeSeverity,
    StoryMaturity,
)
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    StakeFactory,
    StakeResolutionFactory,
    TransitionFactory,
    seed_default_risk_calibrations,
)
from world.stories.models import TransitionRequiredOutcome
from world.stories.services.stakes import compute_effective_risk, validate_stakes_readiness


class ComputeEffectiveRiskTests(TestCase):
    def test_none_stays_none(self):
        self.assertEqual(compute_effective_risk(RenownRisk.NONE, 4, 10), RenownRisk.NONE)

    def test_at_level_keeps_declared(self):
        self.assertEqual(compute_effective_risk(RenownRisk.EXTREME, 4, 4), RenownRisk.EXTREME)

    def test_overleveled_decays_one_tier_per_two_levels(self):
        self.assertEqual(compute_effective_risk(RenownRisk.EXTREME, 4, 6), RenownRisk.HIGH)
        self.assertEqual(compute_effective_risk(RenownRisk.EXTREME, 4, 10), RenownRisk.LOW)

    def test_grossly_overleveled_hits_none(self):
        self.assertEqual(compute_effective_risk(RenownRisk.HIGH, 4, 12), RenownRisk.NONE)

    def test_underleveled_upgrade_is_capped_at_one_tier(self):
        self.assertEqual(compute_effective_risk(RenownRisk.MODERATE, 6, 2), RenownRisk.HIGH)

    def test_upgrade_never_exceeds_extreme(self):
        self.assertEqual(compute_effective_risk(RenownRisk.EXTREME, 6, 2), RenownRisk.EXTREME)


class ValidateStakesReadinessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_default_risk_calibrations()

    def _staked_beat(self, risk=RenownRisk.HIGH, target_level=4):
        return BeatFactory(
            risk=risk,
            target_level=target_level,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
        )

    def _complete_stake(self, beat, severity=StakeSeverity.DIRE):
        stake = StakeFactory(beat=beat, severity=severity)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        return stake

    def test_unstaked_beat_is_trivially_ready(self):
        report = validate_stakes_readiness(BeatFactory(risk=RenownRisk.NONE))
        self.assertFalse(report.is_staked)
        self.assertTrue(report.is_ready)

    def test_missing_target_level_blocks(self):
        beat = self._staked_beat(target_level=None)
        self._complete_stake(beat, severity=StakeSeverity.REMOVAL)
        report = validate_stakes_readiness(beat)
        self.assertFalse(report.is_ready)
        self.assertTrue(any("target_level" in p for p in report.problems))

    def test_missing_loss_column_blocks(self):
        beat = self._staked_beat()
        stake = StakeFactory(beat=beat, severity=StakeSeverity.REMOVAL)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        report = validate_stakes_readiness(beat)
        self.assertFalse(report.is_ready)

    def test_severity_floor_blocks_fake_stakes(self):
        beat = self._staked_beat()  # HIGH: floor_total=4
        self._complete_stake(beat, severity=StakeSeverity.SETBACK)  # total 1 < 4
        report = validate_stakes_readiness(beat)
        self.assertFalse(report.is_ready)

    def test_severity_ceiling_blocks_overreach(self):
        beat = self._staked_beat(risk=RenownRisk.LOW)  # LOW: ceiling=COSTLY
        self._complete_stake(beat, severity=StakeSeverity.REMOVAL)
        report = validate_stakes_readiness(beat)
        self.assertFalse(report.is_ready)

    def test_extreme_requires_removal_on_the_beat_itself(self):
        beat = self._staked_beat(risk=RenownRisk.EXTREME)  # hops=0, floor 6
        self._complete_stake(beat, severity=StakeSeverity.DIRE)
        self._complete_stake(beat, severity=StakeSeverity.COSTLY)  # total 6, no REMOVAL
        report = validate_stakes_readiness(beat)
        self.assertFalse(report.is_ready)
        self._complete_stake(beat, severity=StakeSeverity.REMOVAL)
        self.assertTrue(validate_stakes_readiness(beat).is_ready)

    def test_fuse_walk_finds_removal_downstream_at_outline(self):
        # HIGH (hops=1): negotiation beat; failure routes to a hard-fight
        # episode (OUTLINE) whose beat carries a REMOVAL stake.
        beat = self._staked_beat(risk=RenownRisk.HIGH)
        self._complete_stake(beat, severity=StakeSeverity.DIRE)  # total 4, no REMOVAL here
        fight_episode = EpisodeFactory(chapter=beat.episode.chapter, maturity=StoryMaturity.OUTLINE)
        transition = TransitionFactory(source_episode=beat.episode, target_episode=fight_episode)
        TransitionRequiredOutcome.objects.create(
            transition=transition, beat=beat, required_outcome=BeatOutcome.FAILURE
        )
        fight_beat = BeatFactory(episode=fight_episode, risk=RenownRisk.EXTREME)
        StakeFactory(beat=fight_beat, severity=StakeSeverity.REMOVAL)
        self.assertTrue(validate_stakes_readiness(beat).is_ready)

    def test_fuse_walk_ignores_pitch_episodes_and_respects_hops(self):
        beat = self._staked_beat(risk=RenownRisk.HIGH)
        self._complete_stake(beat, severity=StakeSeverity.DIRE)
        pitch_episode = EpisodeFactory(chapter=beat.episode.chapter, maturity=StoryMaturity.PITCH)
        TransitionFactory(source_episode=beat.episode, target_episode=pitch_episode)
        removal_beat = BeatFactory(episode=pitch_episode, risk=RenownRisk.EXTREME)
        StakeFactory(beat=removal_beat, severity=StakeSeverity.REMOVAL)
        report = validate_stakes_readiness(beat)
        self.assertFalse(report.is_ready)  # PITCH doesn't count as authored
