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
from world.currency.models import CurrencyTransfer
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
        character=sheet, character_class=CharacterClassFactory(), level=level
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
        # Ledger honesty (#1770 PR3 review): the reason names a stake reward,
        # not a mission reward.
        ledger_row = CurrencyTransfer.objects.get(to_purse=purse)
        self.assertEqual(ledger_row.reason, f"stake reward: stake:{stake.pk}")
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

    def test_non_win_resolution_rejected(self):
        """WIN-column only (#1770 PR3 review) — a LOSS consolation line is refused."""
        loss = StakeResolutionFactory(stake=self.win.stake, column=StakeResolutionColumn.LOSS)
        resp = self._post_line(self.staff, resolution=loss.pk)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("WIN-column", str(resp.data))

    def test_model_clean_rejects_non_win_resolution(self):
        from django.core.exceptions import ValidationError

        from world.stories.models import StakeRewardLine

        loss = StakeResolutionFactory(stake=self.win.stake, column=StakeResolutionColumn.WITHDRAWAL)
        line = StakeRewardLine(resolution=loss, sink=StakeRewardSink.MONEY, amount=10)
        with self.assertRaises(ValidationError):
            line.clean()


class CompletedBeatEditRefusalTests(APITestCase):
    """#1770 PR3 review finding 1a: contract editing ends when the beat completes.

    The open-activation lock alone leaves a hole — the completion tail closes
    the activation while stakes still pend for a GM pick, which would reopen
    reward-line (and resolution) editing on a contract that already ran.
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        story = StoryFactory(owners=[cls.staff])
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        cls.beat = BeatFactory(episode=episode)
        cls.stake = StakeFactory(beat=cls.beat)
        cls.win = StakeResolutionFactory(stake=cls.stake, column=StakeResolutionColumn.WIN)
        cls.line = StakeRewardLineFactory(resolution=cls.win, amount=100)

    def _complete_beat(self):
        # Mutate the canonical ORM instance, not the per-test TestData copy —
        # the serializer walks the idmapper-cached Beat, which a copy's
        # .save() would leave stale.
        from world.stories.models import Beat

        beat = Beat.objects.get(pk=self.beat.pk)
        beat.outcome = BeatOutcome.PENDING_GM_REVIEW
        beat.save(update_fields=["outcome"])

    def test_reward_line_create_refused_after_completion(self):
        self._complete_beat()
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("stakerewardline-list"),
            {"resolution": self.win.pk, "sink": StakeRewardSink.MONEY, "amount": 100},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("completed", str(resp.data))

    def test_reward_line_update_refused_after_completion(self):
        self._complete_beat()
        self.client.force_authenticate(user=self.staff)
        resp = self.client.patch(
            reverse("stakerewardline-detail", kwargs={"pk": self.line.pk}),
            {"amount": 99999},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("completed", str(resp.data))

    def test_resolution_write_refused_after_completion(self):
        """Same hole on StakeResolution: no re-authoring branches post-completion."""
        self._complete_beat()
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            reverse("stakeresolution-list"),
            {"stake": self.stake.pk, "column": StakeResolutionColumn.WITHDRAWAL},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("completed", str(resp.data))


class PayTimeBandRecheckTests(EvenniaTestCase):
    """#1770 PR3 review finding 1b: the payout re-verifies the reward band.

    The activation's frozen is_ready verdict can go stale in the
    pending-GM-pick window; an out-of-band live total skips the payout.
    """

    @classmethod
    def setUpTestData(cls):
        seed_default_risk_calibrations()
        cls.gm_profile = GMProfileFactory()

    def test_out_of_band_at_pay_time_skips_payout(self):
        sheet, beat, progress, stake, win = _character_story_ready_beat(money=300)
        _level_sheet(sheet, 4)
        activation = activate_stakes_contract(beat, [sheet])
        self.assertTrue(activation.is_ready)
        record_outcome_tier_completion(
            progress=progress, beat=beat, force_outcome=BeatOutcome.PENDING_GM_REVIEW
        )

        # Simulate the bypass: the line changes after the contract ran
        # (e.g. via admin or a pre-fix API); HIGH's ceiling is 1500.
        line = win.reward_lines.get()
        line.amount = 5000
        line.save(update_fields=["amount"])

        outcome = resolve_stake_by_gm_pick(
            stake, column=StakeResolutionColumn.WIN, gm_profile=self.gm_profile
        )

        self.assertEqual(outcome.column, StakeResolutionColumn.WIN)
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 0)


class ClaimBeforePayTests(EvenniaTestCase):
    """#1770 PR3 review finding 2: the StakeOutcome claim precedes any firing.

    A losing concurrent create must return the winner's row WITHOUT firing
    pool/writers/rewards again — the purse holds one payout, never two.
    """

    @classmethod
    def setUpTestData(cls):
        seed_default_risk_calibrations()

    def test_double_fire_pays_once(self):
        from world.stories.constants import StakeOutcomeMethod
        from world.stories.services.stake_resolution import _fire_branch_and_record

        sheet, beat, _progress, stake, win = _character_story_ready_beat(money=300)
        _level_sheet(sheet, 4)
        activation = activate_stakes_contract(beat, [sheet])
        persona = sheet.primary_persona

        def fire():
            return _fire_branch_and_record(
                stake=stake,
                resolution=win,
                column=StakeResolutionColumn.WIN,
                method=StakeOutcomeMethod.MACHINE,
                activation=activation,
                progress=None,
                scope=StoryScope.CHARACTER,
                participants=[persona],
            )

        first = fire()
        second = fire()  # simulates the loser whose .exists() pre-check missed

        self.assertEqual(second.pk, first.pk)
        self.assertEqual(StakeOutcome.objects.filter(stake=stake).count(), 1)
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 300)  # paid once, not 600


class GMPickGateAndActivationTests(EvenniaTestCase):
    """GM picks honor the anti-farming gate and resolve under the activation
    the stake actually pended with (#1770 PR3 review findings 3 + 5)."""

    @classmethod
    def setUpTestData(cls):
        seed_default_risk_calibrations()
        cls.gm_profile = GMProfileFactory()

    def _pend(self, progress, beat):
        record_outcome_tier_completion(
            progress=progress, beat=beat, force_outcome=BeatOutcome.PENDING_GM_REVIEW
        )

    def test_pick_under_unready_activation_skips_payout(self):
        sheet, beat, progress, stake, _win = _character_story_ready_beat(
            target_level=None, money=300
        )
        _level_sheet(sheet, 4)
        activation = activate_stakes_contract(beat, [sheet])
        self.assertFalse(activation.is_ready)
        self._pend(progress, beat)

        outcome = resolve_stake_by_gm_pick(
            stake, column=StakeResolutionColumn.WIN, gm_profile=self.gm_profile
        )

        self.assertEqual(outcome.column, StakeResolutionColumn.WIN)
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 0)

    def test_pick_under_effective_none_activation_skips_payout(self):
        sheet, beat, progress, stake, _win = _character_story_ready_beat(money=300)
        _level_sheet(sheet, 12)  # target 4 + 8 over -> effective NONE
        activation = activate_stakes_contract(beat, [sheet])
        self.assertEqual(activation.effective_risk, RenownRisk.NONE)
        self._pend(progress, beat)

        resolve_stake_by_gm_pick(
            stake, column=StakeResolutionColumn.WIN, gm_profile=self.gm_profile
        )

        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 0)

    def test_pick_uses_activation_of_the_pended_completion(self):
        """A new activation opened AFTER the pend (beat re-engaged) must not
        change the pended stake's gate or its audit row."""
        sheet, beat, progress, stake, _win = _character_story_ready_beat(money=300)
        _level_sheet(sheet, 4)
        pended_under = activate_stakes_contract(beat, [sheet])
        self.assertEqual(pended_under.effective_risk, RenownRisk.HIGH)
        self._pend(progress, beat)

        # Beat re-engaged by a grossly over-leveled party: a NEW open
        # activation at effective NONE. The old selection logic (open
        # activation first) would starve the pended stake's payout.
        overleveled = _level_sheet(CharacterSheetFactory(), 12)
        later = activate_stakes_contract(beat, [overleveled])
        self.assertIsNone(later.resolved_at)
        self.assertEqual(later.effective_risk, RenownRisk.NONE)

        outcome = resolve_stake_by_gm_pick(
            stake, column=StakeResolutionColumn.WIN, gm_profile=self.gm_profile
        )

        self.assertEqual(outcome.activation_id, pended_under.pk)
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 300)
