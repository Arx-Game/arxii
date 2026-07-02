"""Tests for two-sided contract WIN rewards (#1770 PR3).

Covers the E2E win payout (money + resonance to every participant), the
anti-farming gate (no activation / unready / effective NONE pays nothing while
loss consequences keep firing), the GM constrained pick honoring the same
gate, and the StakeRewardLine serializer gates (lock, ownership, sink shape).
"""

from django.urls import reverse
from evennia.utils.test_resources import EvenniaTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.currency.services import get_or_create_purse
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.magic.constants import GainSource
from world.magic.factories import ResonanceFactory
from world.magic.models import CharacterResonance, ResonanceGrant
from world.societies.constants import RenownRisk
from world.societies.factories import LegendSourceTypeFactory
from world.societies.models import LegendEvent
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    StakeResolutionColumn,
    StakeRewardSink,
    StakeSeverity,
    StoryMaturity,
    StoryScope,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    GroupStoryProgressFactory,
    StakeFactory,
    StakeResolutionFactory,
    StakeRewardLineFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    seed_default_risk_calibrations,
)
from world.stories.models import StakeContractActivation, StakeOutcome, TransitionRequiredOutcome
from world.stories.services.beats import record_outcome_tier_completion
from world.stories.services.stake_resolution import resolve_stake_by_gm_pick
from world.stories.services.stakes import activate_stakes_contract
from world.traits.factories import CheckOutcomeFactory


def _level_sheet(sheet, level):
    """Give ``sheet`` a CharacterClassLevel so _character_level reads ``level``."""
    CharacterClassLevelFactory(
        character=sheet.character, character_class=CharacterClassFactory(), level=level
    )
    return sheet


def _add_removal_jeopardy(beat):
    """Downstream OUTLINE episode with a REMOVAL stake, one failure hop away."""
    fight_episode = EpisodeFactory(chapter=beat.episode.chapter, maturity=StoryMaturity.OUTLINE)
    transition = TransitionFactory(source_episode=beat.episode, target_episode=fight_episode)
    TransitionRequiredOutcome.objects.create(
        transition=transition, beat=beat, required_outcome=BeatOutcome.FAILURE
    )
    fight_beat = BeatFactory(episode=fight_episode, risk=RenownRisk.EXTREME)
    StakeFactory(beat=fight_beat, severity=StakeSeverity.REMOVAL)


def _character_story_ready_beat(*, target_level=4, money=300, resonance_amount=0, resonance=None):
    """A CHARACTER-scope story whose HIGH beat clears readiness with reward lines.

    Returns (sheet, beat, progress, stake, win_resolution). Reward total must
    stay within HIGH's seeded band (300..1500) for the contract to be ready.
    """
    sheet = CharacterSheetFactory()
    story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
    chapter = ChapterFactory(story=story)
    episode = EpisodeFactory(chapter=chapter)
    beat = BeatFactory(
        episode=episode,
        risk=RenownRisk.HIGH,
        target_level=target_level,
        predicate_type=BeatPredicateType.OUTCOME_TIER,
    )
    progress = StoryProgressFactory(story=story, character_sheet=sheet)
    stake = StakeFactory(beat=beat, severity=StakeSeverity.DIRE)
    win = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
    StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
    if money:
        StakeRewardLineFactory(resolution=win, sink=StakeRewardSink.MONEY, amount=money)
    if resonance_amount:
        StakeRewardLineFactory(
            resolution=win,
            sink=StakeRewardSink.RESONANCE,
            amount=resonance_amount,
            resonance=resonance,
        )
    _add_removal_jeopardy(beat)
    return sheet, beat, progress, stake, win


class WinRewardE2ETests(EvenniaTestCase):
    """Staked ready beat, activated at level, SUCCESS -> the contract pays."""

    @classmethod
    def setUpTestData(cls):
        seed_default_risk_calibrations()
        cls.win_tier = CheckOutcomeFactory(name="Reward Triumph", success_level=3)
        cls.fail_tier = CheckOutcomeFactory(name="Reward Rout", success_level=-2)

    def test_win_pays_money_and_resonance_to_participant(self):
        resonance = ResonanceFactory()
        sheet, beat, progress, stake, _win = _character_story_ready_beat(
            money=300, resonance_amount=100, resonance=resonance
        )
        _level_sheet(sheet, 4)
        activation = activate_stakes_contract(beat, [sheet])
        self.assertTrue(activation.is_ready)
        self.assertEqual(activation.effective_risk, RenownRisk.HIGH)

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.win_tier)

        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.WIN)
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 300)
        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual(cr.balance, 100)
        grant = ResonanceGrant.objects.get(character_sheet=sheet)
        self.assertEqual(grant.source, GainSource.STAKE_REWARD)
        self.assertEqual(grant.amount, 100)

    def test_loss_pays_nothing(self):
        sheet, beat, progress, stake, _win = _character_story_ready_beat(money=300)
        _level_sheet(sheet, 4)
        activate_stakes_contract(beat, [sheet])

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.fail_tier)

        self.assertEqual(StakeOutcome.objects.get(stake=stake).column, StakeResolutionColumn.LOSS)
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 0)


class AntiFarmingGateTests(EvenniaTestCase):
    """Pillars 4/7/8: only a ready, effective-risk-bearing activation pays."""

    @classmethod
    def setUpTestData(cls):
        seed_default_risk_calibrations()
        cls.win_tier = CheckOutcomeFactory(name="Farm Triumph", success_level=3)
        cls.fail_tier = CheckOutcomeFactory(name="Farm Rout", success_level=-2)

    def test_unready_activation_win_pays_nothing(self):
        """target_level undeclared -> unready -> effective NONE -> no payout."""
        sheet, beat, progress, stake, _win = _character_story_ready_beat(
            target_level=None, money=300
        )
        _level_sheet(sheet, 4)
        activation = activate_stakes_contract(beat, [sheet])
        self.assertFalse(activation.is_ready)
        self.assertEqual(activation.effective_risk, RenownRisk.NONE)

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.win_tier)

        self.assertEqual(StakeOutcome.objects.get(stake=stake).column, StakeResolutionColumn.WIN)
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 0)

    def test_unready_activation_loss_consequences_still_fire(self):
        """The gate only starves the payout — losing still hurts (pillar 7)."""
        sheet, beat, progress, stake, _win = _character_story_ready_beat(
            target_level=None, money=300
        )
        consequence = ConsequenceFactory(outcome_tier=self.fail_tier)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=10,
            legend_source_type=LegendSourceTypeFactory(),
            legend_description_template="Unready loss still lands.",
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        loss = stake.resolutions.get(column=StakeResolutionColumn.LOSS)
        loss.consequence_pool = pool
        loss.save(update_fields=["consequence_pool"])
        _level_sheet(sheet, 4)
        activate_stakes_contract(beat, [sheet])

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.fail_tier)

        self.assertTrue(LegendEvent.objects.exists())  # the loss pool fired
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 0)

    def test_overleveled_party_effective_none_pays_nothing(self):
        """Ready contract, but the party out-levels it into effective NONE."""
        sheet, beat, progress, stake, _win = _character_story_ready_beat(money=300)
        _level_sheet(sheet, 12)  # target 4 + 8 over -> -4 tiers -> NONE
        activation = activate_stakes_contract(beat, [sheet])
        self.assertTrue(activation.is_ready)
        self.assertEqual(activation.effective_risk, RenownRisk.NONE)

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.win_tier)

        self.assertEqual(StakeOutcome.objects.get(stake=stake).column, StakeResolutionColumn.WIN)
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 0)

    def test_no_activation_pays_nothing(self):
        """A staked beat completed without ever locking the contract pays nothing."""
        sheet, beat, progress, stake, _win = _character_story_ready_beat(money=300)

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.win_tier)

        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.WIN)
        self.assertIsNone(outcome.activation)
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 0)


def _group_story_ready_pending_beat():
    """A GROUP-scope story with a ready, activated HIGH beat pending GM review."""
    story = StoryFactory(scope=StoryScope.GROUP)
    chapter = ChapterFactory(story=story)
    episode = EpisodeFactory(chapter=chapter)
    gm_table = GMTableFactory()
    progress = GroupStoryProgressFactory(story=story, gm_table=gm_table, current_episode=episode)
    beat = BeatFactory(
        episode=episode,
        risk=RenownRisk.HIGH,
        target_level=4,
        predicate_type=BeatPredicateType.OUTCOME_TIER,
    )
    stake = StakeFactory(beat=beat, severity=StakeSeverity.DIRE)
    win = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
    StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
    StakeRewardLineFactory(resolution=win, sink=StakeRewardSink.MONEY, amount=300)
    _add_removal_jeopardy(beat)
    party_sheet = _level_sheet(CharacterSheetFactory(), 4)
    activation = activate_stakes_contract(beat, [party_sheet])
    record_outcome_tier_completion(
        progress=progress, beat=beat, force_outcome=BeatOutcome.PENDING_GM_REVIEW
    )
    return stake, activation


class GMPickRewardTests(EvenniaTestCase):
    """The constrained pick honors the same anti-farming gate (#1770 PR3)."""

    @classmethod
    def setUpTestData(cls):
        seed_default_risk_calibrations()
        cls.gm_profile = GMProfileFactory()

    def test_group_pick_win_with_participants_pays(self):
        stake, activation = _group_story_ready_pending_beat()
        self.assertTrue(activation.is_ready)
        persona = CharacterSheetFactory().primary_persona

        resolve_stake_by_gm_pick(
            stake,
            column=StakeResolutionColumn.WIN,
            gm_profile=self.gm_profile,
            participants=[persona],
        )

        purse = get_or_create_purse(persona.character_sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 300)

    def test_group_pick_win_without_participants_skips_payout(self):
        stake, _activation = _group_story_ready_pending_beat()

        outcome = resolve_stake_by_gm_pick(
            stake, column=StakeResolutionColumn.WIN, gm_profile=self.gm_profile
        )

        self.assertEqual(outcome.column, StakeResolutionColumn.WIN)
        # No participants resolved -> the payout is skipped, never a crash.
        self.assertFalse(ResonanceGrant.objects.exists())


class StakeRewardLineSerializerTests(APITestCase):
    """Lock refusal, ownership walk, and sink/resonance shape (#1770 PR3)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.owner = AccountFactory(is_staff=False)
        cls.outsider = AccountFactory(is_staff=False)
        story = StoryFactory(owners=[cls.owner])
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        cls.beat = BeatFactory(episode=episode)
        stake = StakeFactory(beat=cls.beat)
        cls.win = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)

    def _post_line(self, user, **extra):
        self.client.force_authenticate(user=user)
        payload = {
            "resolution": self.win.pk,
            "sink": StakeRewardSink.MONEY,
            "amount": 100,
            **extra,
        }
        return self.client.post(reverse("stakerewardline-list"), payload, format="json")

    def test_owner_creates_money_line(self):
        resp = self._post_line(self.owner)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["sink"], StakeRewardSink.MONEY)

    def test_outsider_rejected(self):
        resp = self._post_line(self.outsider)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("permission", str(resp.data))

    def test_locked_beat_refuses_writes(self):
        StakeContractActivation.objects.create(
            beat=self.beat,
            party_average_level=4,
            declared_target_level=4,
            declared_risk=RenownRisk.HIGH,
            effective_risk=RenownRisk.HIGH,
            is_ready=True,
        )
        resp = self._post_line(self.staff)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("locked", str(resp.data))

    def test_resonance_sink_requires_resonance(self):
        resp = self._post_line(self.staff, sink=StakeRewardSink.RESONANCE)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("resonance", str(resp.data))

    def test_money_sink_forbids_resonance(self):
        resonance = ResonanceFactory()
        resp = self._post_line(self.staff, resonance=resonance.pk)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only allowed", str(resp.data))

    def test_amount_must_be_positive(self):
        resp = self._post_line(self.staff, amount=0)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", str(resp.data))
