"""Service tests for the stakes contract engine (#1770 PR1)."""

from unittest import mock

from django.test import TestCase
from evennia.utils.test_resources import EvenniaTestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import ConsequenceFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
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
    StakeFactory,
    StakeResolutionFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    seed_default_risk_calibrations,
)
from world.stories.models import TransitionRequiredOutcome
from world.stories.services.beats import record_outcome_tier_completion
from world.stories.services.stakes import (
    activate_stakes_contract,
    compute_effective_risk,
    effective_risk_for_beat,
    get_open_activation,
    validate_stakes_readiness,
)
from world.traits.factories import CheckOutcomeFactory


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

    def test_fuse_walk_finds_character_loss_pool_downstream(self):
        # HIGH (hops=1): same shape as the REMOVAL-stake case above, but the
        # downstream OUTLINE beat carries no REMOVAL stake at all — the
        # jeopardy signal instead comes from a character_loss=True Consequence
        # sitting in its failure_consequences pool (#1770 chain-rule fold-in).
        beat = self._staked_beat(risk=RenownRisk.HIGH)
        self._complete_stake(beat, severity=StakeSeverity.DIRE)  # total 4, no REMOVAL here
        fight_episode = EpisodeFactory(chapter=beat.episode.chapter, maturity=StoryMaturity.OUTLINE)
        transition = TransitionFactory(source_episode=beat.episode, target_episode=fight_episode)
        TransitionRequiredOutcome.objects.create(
            transition=transition, beat=beat, required_outcome=BeatOutcome.FAILURE
        )
        consequence = ConsequenceFactory(character_loss=True)
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        fight_beat = BeatFactory(
            episode=fight_episode, risk=RenownRisk.EXTREME, failure_consequences=pool
        )
        self.assertFalse(fight_beat.stakes.filter(severity=StakeSeverity.REMOVAL).exists())
        self.assertTrue(validate_stakes_readiness(beat).is_ready)


class ActivationTests(EvenniaTestCase):
    @classmethod
    def setUpTestData(cls):
        seed_default_risk_calibrations()

    def _ready_beat(self, risk=RenownRisk.HIGH, target_level=4):
        """A beat that actually clears validate_stakes_readiness at HIGH risk.

        HIGH's ceiling (4) is below REMOVAL's severity (5), so a HIGH beat can
        never wager REMOVAL directly on itself and stay under the ceiling —
        jeopardy must be reached via the fuse walk instead (same shape as
        ``test_fuse_walk_finds_removal_downstream_at_outline`` above): a DIRE
        stake here (total 4, meets floor and ceiling) plus a downstream OUTLINE
        beat carrying the REMOVAL stake, one failure-hop away.
        """
        beat = BeatFactory(
            risk=risk,
            target_level=target_level,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
        )
        stake = StakeFactory(beat=beat, severity=StakeSeverity.DIRE)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        fight_episode = EpisodeFactory(chapter=beat.episode.chapter, maturity=StoryMaturity.OUTLINE)
        transition = TransitionFactory(source_episode=beat.episode, target_episode=fight_episode)
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
            CharacterClassLevelFactory(
                character=sheet.character, character_class=char_class, level=level
            )
            sheets.append(sheet)
        return sheets

    def test_activation_computes_effective_risk_from_party(self):
        beat = self._ready_beat()
        sheets = self._sheets_at_levels(8, 8)  # target 4 + 4 over → -2 tiers
        activation = activate_stakes_contract(beat, sheets)
        self.assertEqual(activation.declared_risk, RenownRisk.HIGH)
        self.assertEqual(activation.effective_risk, RenownRisk.LOW)

    def test_unready_contract_downgrades_to_none(self):
        beat = BeatFactory(
            risk=RenownRisk.HIGH,
            target_level=4,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
        )  # no stakes at all
        sheets = self._sheets_at_levels(4, 4)
        activation = activate_stakes_contract(beat, sheets)
        self.assertFalse(activation.is_ready)
        self.assertEqual(activation.effective_risk, RenownRisk.NONE)
        self.assertIn("no stakes declared", activation.readiness_notes)

    def test_activation_is_idempotent_while_open(self):
        beat = self._ready_beat()
        sheets = self._sheets_at_levels(4, 4)
        first = activate_stakes_contract(beat, sheets)
        second = activate_stakes_contract(beat, sheets)
        self.assertEqual(first.pk, second.pk)

    def test_effective_risk_for_beat_prefers_open_activation(self):
        beat = self._ready_beat()
        self.assertEqual(effective_risk_for_beat(beat), RenownRisk.HIGH)  # no activation
        sheets = self._sheets_at_levels(8, 8)
        activate_stakes_contract(beat, sheets)  # → LOW
        self.assertEqual(effective_risk_for_beat(beat), RenownRisk.LOW)

    def test_activate_requires_at_least_one_participant(self):
        beat = self._ready_beat()
        with self.assertRaises(ValueError):
            activate_stakes_contract(beat, [])

    def test_completion_tail_resolves_open_activation(self):
        """record_outcome_tier_completion on a beat with an open activation closes it."""
        decisive = CheckOutcomeFactory(name="Decisive Victory Activation", success_level=6)
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = self._ready_beat()
        beat.episode = episode
        beat.save(update_fields=["episode"])
        progress = StoryProgressFactory(story=story, character_sheet=sheet)

        sheets = self._sheets_at_levels(4, 4)
        activation = activate_stakes_contract(beat, sheets)
        self.assertIsNone(activation.resolved_at)
        self.assertIsNotNone(get_open_activation(beat))

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=decisive)

        activation.refresh_from_db()
        self.assertIsNotNone(activation.resolved_at)
        self.assertIsNone(get_open_activation(beat))

    def test_activation_race_returns_existing_row(self):
        """A losing concurrent create re-fetches and returns the winner's row.

        Simulates the race by forcing the up-front idempotency check to miss
        (as if a concurrent caller's create hadn't landed yet when this one
        checked) even though a row already exists — so this call's own
        ``.create()`` collides with ``unique_open_activation_per_beat`` and
        must recover via the real ``get_open_activation`` instead of letting
        the ``IntegrityError`` escape.
        """
        beat = self._ready_beat()
        sheets = self._sheets_at_levels(4, 4)
        existing = activate_stakes_contract(beat, sheets)

        real_get_open_activation = get_open_activation
        with mock.patch(
            "world.stories.services.stakes.get_open_activation",
            side_effect=[None, real_get_open_activation(beat)],
        ):
            result = activate_stakes_contract(beat, sheets)

        self.assertEqual(result.pk, existing.pk)
