"""Tests for per-stake resolution (#1770 PR2).

Covers machine grading through the completion tail (record_outcome_tier_completion
and record_gm_marked_outcome), the NPC-vitals LOSS override, withdrawal handling,
the GM constrained pick (service + endpoint), the pillar-12 no-fiat serializer
guard, the world-state writers, and stake-level transition routing.
"""

from django.urls import reverse
from django.utils import timezone
from evennia.utils.test_resources import EvenniaTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import AccountFactory
from world.boundaries.factories import TreasuredSubjectFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.npc_services.models import NPCStanding
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.societies.factories import LegendSourceTypeFactory
from world.societies.models import LegendEvent
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    StakeOutcomeMethod,
    StakeResolutionColumn,
    StakeSubjectKind,
    StoryScope,
    TransitionMode,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    GroupStoryProgressFactory,
    StakeFactory,
    StakeOutcomeFactory,
    StakeResolutionFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    TreasuredSignoffFactory,
    seed_default_risk_calibrations,
)
from world.stories.models import StakeOutcome, TransitionRequiredOutcome
from world.stories.services.beats import (
    record_gm_marked_outcome,
    record_outcome_tier_completion,
)
from world.stories.services.stake_resolution import resolve_stake_by_gm_pick
from world.stories.services.stakes import activate_stakes_contract, get_open_activation
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory


def _character_story_beat(**beat_kwargs):
    """A CHARACTER-scope story with an OUTCOME_TIER beat and active progress."""
    sheet = CharacterSheetFactory()
    story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
    chapter = ChapterFactory(story=story)
    episode = EpisodeFactory(chapter=chapter)
    beat_kwargs.setdefault("predicate_type", BeatPredicateType.OUTCOME_TIER)
    beat = BeatFactory(episode=episode, **beat_kwargs)
    progress = StoryProgressFactory(story=story, character_sheet=sheet)
    return sheet, beat, progress


class MachineGradingTests(EvenniaTestCase):
    """resolve_stakes_for_completion through record_outcome_tier_completion."""

    @classmethod
    def setUpTestData(cls):
        seed_default_risk_calibrations()
        cls.fail_tier = CheckOutcomeFactory(name="Stake Rout", success_level=-2)
        cls.win_tier = CheckOutcomeFactory(name="Stake Triumph", success_level=3)

    def test_loss_branch_fires_pool_and_writes_machine_outcome(self):
        """E2E: a staked beat failing fires the LOSS branch pool, writes the
        StakeOutcome audit row (method=MACHINE, activation FK), and the
        completion tail still closes the activation afterwards."""
        sheet, beat, progress = _character_story_beat()
        stake = StakeFactory(beat=beat)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        consequence = ConsequenceFactory(outcome_tier=self.fail_tier)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=10,
            legend_source_type=LegendSourceTypeFactory(),
            legend_description_template="Stake lost.",
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        loss_branch = StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, consequence_pool=pool
        )
        activation = activate_stakes_contract(beat, [sheet])

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.fail_tier)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.FAILURE)
        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.LOSS)
        self.assertEqual(outcome.method, StakeOutcomeMethod.MACHINE)
        self.assertEqual(outcome.resolution_id, loss_branch.pk)
        self.assertEqual(outcome.activation_id, activation.pk)
        self.assertTrue(LegendEvent.objects.exists())  # the stake pool fired
        self.assertIsNone(get_open_activation(beat))  # tail still closed the lock

    def test_success_grades_win_column(self):
        _sheet, beat, progress = _character_story_beat()
        stake = StakeFactory(beat=beat)
        win_branch = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.win_tier)

        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.WIN)
        self.assertEqual(outcome.resolution_id, win_branch.pk)

    def test_missing_branch_records_null_resolution(self):
        """Audit honesty: an unready contract that ran anyway still gets a row."""
        _sheet, beat, progress = _character_story_beat()
        stake = StakeFactory(beat=beat)  # no resolutions authored at all

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.fail_tier)

        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.LOSS)
        self.assertIsNone(outcome.resolution)

    def test_idempotent_skips_already_resolved_stake(self):
        """A stake with an earlier StakeOutcome (e.g. a GM pick) is untouched."""
        _sheet, beat, progress = _character_story_beat()
        stake = StakeFactory(beat=beat)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        prior = StakeOutcomeFactory(
            stake=stake,
            column=StakeResolutionColumn.WIN,
            method=StakeOutcomeMethod.GM_PICK,
        )

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.fail_tier)

        outcomes = list(StakeOutcome.objects.filter(stake=stake))
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].pk, prior.pk)
        self.assertEqual(outcomes[0].column, StakeResolutionColumn.WIN)

    def test_pending_gm_review_defers_stakes(self):
        """force_outcome=PENDING_GM_REVIEW (no withdrawal): stakes wait for the GM."""
        _sheet, beat, progress = _character_story_beat()
        stake = StakeFactory(beat=beat)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)

        record_outcome_tier_completion(
            progress=progress, beat=beat, force_outcome=BeatOutcome.PENDING_GM_REVIEW
        )

        self.assertFalse(StakeOutcome.objects.filter(stake=stake).exists())

    def test_npc_fate_dead_subject_grades_loss_even_on_beat_success(self):
        """Pillar 11 (#1760: generalized to the LifecycleState ladder — the
        old implicit is-dead override is gone; reproducing it now requires an
        explicitly authored machine_match_lifecycle_state=DEAD branch)."""
        _sheet, beat, progress = _character_story_beat()
        npc_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=npc_sheet, life_state=CharacterLifeState.DEAD)
        npc_sheet.lifecycle_state = LifecycleState.DEAD
        npc_sheet.save(update_fields=["lifecycle_state"])
        npc_stake = StakeFactory(
            beat=beat, subject_kind=StakeSubjectKind.NPC_FATE, subject_sheet=npc_sheet
        )
        npc_loss = StakeResolutionFactory(
            stake=npc_stake,
            column=StakeResolutionColumn.LOSS,
            machine_match_lifecycle_state=LifecycleState.DEAD,
        )
        StakeResolutionFactory(stake=npc_stake, column=StakeResolutionColumn.WIN)
        other_stake = StakeFactory(beat=beat)
        other_win = StakeResolutionFactory(stake=other_stake, column=StakeResolutionColumn.WIN)

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.win_tier)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        npc_outcome = StakeOutcome.objects.get(stake=npc_stake)
        self.assertEqual(npc_outcome.column, StakeResolutionColumn.LOSS)
        self.assertEqual(npc_outcome.resolution_id, npc_loss.pk)
        other_outcome = StakeOutcome.objects.get(stake=other_stake)
        self.assertEqual(other_outcome.column, StakeResolutionColumn.WIN)
        self.assertEqual(other_outcome.resolution_id, other_win.pk)

    def test_captured_lifecycle_state_selects_matching_branch_over_default(self) -> None:
        """A NPC_FATE stake whose subject is CAPTURED fires the branch whose
        machine_match_lifecycle_state=CAPTURED, not the plain LOSS default."""
        subject = CharacterSheetFactory()
        subject.lifecycle_state = LifecycleState.CAPTURED
        subject.save(update_fields=["lifecycle_state"])
        beat = BeatFactory(predicate_type=BeatPredicateType.GM_MARKED)
        stake = StakeFactory(
            beat=beat, subject_kind=StakeSubjectKind.NPC_FATE, subject_sheet=subject
        )
        captured_branch = StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            outcome_key="captured",
            machine_match_lifecycle_state=LifecycleState.CAPTURED,
        )
        StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            outcome_key="",
        )

        story = beat.episode.chapter.story
        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(story=story, character_sheet=sheet)
        record_gm_marked_outcome(
            progress=progress,
            beat=beat,
            outcome=BeatOutcome.SUCCESS,
        )

        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.resolution_id, captured_branch.pk)

    def test_withdrawal_fires_authored_branch_and_pends_the_rest(self):
        _sheet, beat, progress = _character_story_beat()
        authored = StakeFactory(beat=beat)
        branch = StakeResolutionFactory(stake=authored, column=StakeResolutionColumn.WITHDRAWAL)
        unauthored = StakeFactory(beat=beat)

        record_outcome_tier_completion(
            progress=progress,
            beat=beat,
            force_outcome=BeatOutcome.PENDING_GM_REVIEW,
            withdrawal=True,
        )

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.PENDING_GM_REVIEW)
        outcome = StakeOutcome.objects.get(stake=authored)
        self.assertEqual(outcome.column, StakeResolutionColumn.WITHDRAWAL)
        self.assertEqual(outcome.method, StakeOutcomeMethod.MACHINE)
        self.assertEqual(outcome.resolution_id, branch.pk)
        self.assertFalse(StakeOutcome.objects.filter(stake=unauthored).exists())

    def test_withdrawal_requires_pending_gm_review(self):
        _sheet, beat, progress = _character_story_beat()
        with self.assertRaises(ValueError):
            record_outcome_tier_completion(
                progress=progress, beat=beat, outcome_tier=self.fail_tier, withdrawal=True
            )

    def test_withdrawn_treasured_signoff_routes_stake_to_withdrawal(self):
        """#1771 story 5: a revoked-consent wager never grades against the
        player. A stake whose treasured subject has a WITHDRAWN signoff
        grades WITHDRAWAL at an ORDINARY (non-withdrawal-flag) completion,
        even though the beat resolves SUCCESS; the sibling stake grades WIN
        normally."""
        _sheet, beat, progress = _character_story_beat()
        tenure = RosterTenureFactory()
        treasured = TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        treasured_stake = StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        withdrawal_branch = StakeResolutionFactory(
            stake=treasured_stake, column=StakeResolutionColumn.WITHDRAWAL
        )
        StakeResolutionFactory(stake=treasured_stake, column=StakeResolutionColumn.WIN)
        TreasuredSignoffFactory(
            beat=beat,
            player_data=tenure.player_data,
            treasured_subject=treasured,
            withdrawn_at=timezone.now(),
        )
        ordinary_stake = StakeFactory(beat=beat)
        ordinary_win = StakeResolutionFactory(
            stake=ordinary_stake, column=StakeResolutionColumn.WIN
        )

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.win_tier)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        treasured_outcome = StakeOutcome.objects.get(stake=treasured_stake)
        self.assertEqual(treasured_outcome.column, StakeResolutionColumn.WITHDRAWAL)
        self.assertEqual(treasured_outcome.method, StakeOutcomeMethod.MACHINE)
        self.assertEqual(treasured_outcome.resolution_id, withdrawal_branch.pk)
        ordinary_outcome = StakeOutcome.objects.get(stake=ordinary_stake)
        self.assertEqual(ordinary_outcome.column, StakeResolutionColumn.WIN)
        self.assertEqual(ordinary_outcome.resolution_id, ordinary_win.pk)

    def test_no_matching_tier_row_fires_nothing_but_records_outcome(self):
        """Machine grading is tier-filtered: a branch pool with no consequence
        at the completion's tier applies nothing, but the StakeOutcome is
        still recorded (the resolution happened; its pool had no row for
        this tier). Deliberate asymmetry with the GM-pick/withdrawal paths,
        which apply deterministically (no tier)."""
        _sheet, beat, progress = _character_story_beat()
        other_tier = CheckOutcomeFactory(name="Stake Unmatched Tier", success_level=-5)
        consequence = ConsequenceFactory(outcome_tier=other_tier)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=10,
            legend_source_type=LegendSourceTypeFactory(),
            legend_description_template="Should not fire.",
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        stake = StakeFactory(beat=beat)
        loss_branch = StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, consequence_pool=pool
        )

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.fail_tier)

        self.assertFalse(LegendEvent.objects.exists())  # tier filter kept the pool silent
        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.LOSS)
        self.assertEqual(outcome.resolution_id, loss_branch.pk)

    def test_one_outcome_per_stake_constraint(self):
        """One-outcome-per-stake is enforced at the DB level."""
        from django.db import IntegrityError, transaction

        stake = StakeFactory()
        StakeOutcomeFactory(stake=stake)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StakeOutcomeFactory(stake=stake, column=StakeResolutionColumn.WIN)

    def test_aggregate_crossing_resolves_stakes_and_closes_activation(self):
        """The aggregate-crossing tail resolves stakes at WIN and closes the
        open activation (it must not leave the contract locked forever)."""
        from world.stories.services.beats import record_aggregate_contribution

        sheet, beat, _progress = _character_story_beat(
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=10,
        )
        stake = StakeFactory(beat=beat)
        win_branch = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        activation = activate_stakes_contract(beat, [sheet])
        self.assertIsNone(activation.resolved_at)

        record_aggregate_contribution(beat=beat, character_sheet=sheet, points=10)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.WIN)
        self.assertEqual(outcome.resolution_id, win_branch.pk)
        activation.refresh_from_db()
        self.assertIsNotNone(activation.resolved_at)
        self.assertIsNone(get_open_activation(beat))


class GMPickTests(EvenniaTestCase):
    """resolve_stake_by_gm_pick + the final-mark auto-resolution."""

    @classmethod
    def setUpTestData(cls):
        cls.gm_profile = GMProfileFactory()

    def _pending_staked_beat(self):
        sheet, beat, progress = _character_story_beat()
        stake = StakeFactory(beat=beat)
        win = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        loss = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        record_outcome_tier_completion(
            progress=progress, beat=beat, force_outcome=BeatOutcome.PENDING_GM_REVIEW
        )
        return sheet, beat, progress, stake, win, loss

    def test_pick_fires_branch_and_records_gm(self):
        _sheet, _beat, _progress, stake, win, _loss = self._pending_staked_beat()

        outcome = resolve_stake_by_gm_pick(
            stake,
            column=StakeResolutionColumn.WIN,
            gm_profile=self.gm_profile,
            gm_notes="They earned it.",
        )

        self.assertEqual(outcome.column, StakeResolutionColumn.WIN)
        self.assertEqual(outcome.method, StakeOutcomeMethod.GM_PICK)
        self.assertEqual(outcome.resolution_id, win.pk)
        self.assertEqual(outcome.resolved_by_id, self.gm_profile.pk)
        self.assertEqual(outcome.gm_notes, "They earned it.")

    def test_pick_rejects_unauthored_column(self):
        _sheet, _beat, _progress, stake, _win, loss = self._pending_staked_beat()
        loss.delete()
        with self.assertRaises(ValueError):
            resolve_stake_by_gm_pick(
                stake, column=StakeResolutionColumn.LOSS, gm_profile=self.gm_profile
            )

    def test_second_pick_rejected(self):
        _sheet, _beat, _progress, stake, _win, _loss = self._pending_staked_beat()
        resolve_stake_by_gm_pick(
            stake, column=StakeResolutionColumn.WIN, gm_profile=self.gm_profile
        )
        with self.assertRaises(ValueError):
            resolve_stake_by_gm_pick(
                stake, column=StakeResolutionColumn.LOSS, gm_profile=self.gm_profile
            )

    def test_final_mark_auto_resolves_remaining_but_not_picked(self):
        """After a GM pick, the GM's final mark resolves only the other stakes."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(episode=episode, predicate_type=BeatPredicateType.GM_MARKED)
        progress = StoryProgressFactory(story=story, character_sheet=sheet)

        picked = StakeFactory(beat=beat)
        picked_win = StakeResolutionFactory(stake=picked, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=picked, column=StakeResolutionColumn.LOSS)
        other = StakeFactory(beat=beat)
        StakeResolutionFactory(stake=other, column=StakeResolutionColumn.WIN)
        other_loss = StakeResolutionFactory(stake=other, column=StakeResolutionColumn.LOSS)

        pick = resolve_stake_by_gm_pick(
            picked, column=StakeResolutionColumn.WIN, gm_profile=self.gm_profile
        )

        record_gm_marked_outcome(progress=progress, beat=beat, outcome=BeatOutcome.FAILURE)

        picked_outcomes = list(StakeOutcome.objects.filter(stake=picked))
        self.assertEqual(len(picked_outcomes), 1)
        self.assertEqual(picked_outcomes[0].pk, pick.pk)
        self.assertEqual(picked_outcomes[0].column, StakeResolutionColumn.WIN)
        self.assertEqual(picked_outcomes[0].resolution_id, picked_win.pk)

        other_outcome = StakeOutcome.objects.get(stake=other)
        self.assertEqual(other_outcome.column, StakeResolutionColumn.LOSS)
        self.assertEqual(other_outcome.method, StakeOutcomeMethod.MACHINE)
        self.assertEqual(other_outcome.resolution_id, other_loss.pk)

    def test_gm_pick_selects_the_specific_outcome_key_branch(self) -> None:
        beat = BeatFactory(predicate_type=BeatPredicateType.GM_MARKED)
        stake = StakeFactory(beat=beat)
        destroyed = StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            outcome_key="destroyed",
        )
        StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            outcome_key="captured",
        )
        # resolve_stake_by_gm_pick is a service-level call with no beat-
        # completion precondition (that gate lives in ResolveStakeInputSerializer,
        # covered separately in Step 4's serializer test) — calling it directly
        # against an UNSATISFIED beat is deliberate here.
        gm = GMProfileFactory()
        outcome = resolve_stake_by_gm_pick(
            stake,
            column=StakeResolutionColumn.LOSS,
            outcome_key="destroyed",
            gm_profile=gm,
        )
        self.assertEqual(outcome.resolution_id, destroyed.pk)

    def test_gm_pick_rejects_unauthored_outcome_key_under_authored_column(self) -> None:
        """A column with ONE authored outcome_key doesn't authorize picking another."""
        beat = BeatFactory(predicate_type=BeatPredicateType.GM_MARKED)
        stake = StakeFactory(beat=beat)
        StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            outcome_key="destroyed",
        )
        gm = GMProfileFactory()
        with self.assertRaises(ValueError):
            resolve_stake_by_gm_pick(
                stake,
                column=StakeResolutionColumn.LOSS,
                outcome_key="captured",
                gm_profile=gm,
            )


class ResolveStakeEndpointTests(APITestCase):
    """POST /api/stakes/{id}/resolve/ — the constrained-pick endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory(is_staff=False)
        cls.sheet, cls.beat, cls.progress = _character_story_beat()
        cls.stake = StakeFactory(beat=cls.beat)
        cls.win = StakeResolutionFactory(stake=cls.stake, column=StakeResolutionColumn.WIN)
        record_outcome_tier_completion(
            progress=cls.progress, beat=cls.beat, force_outcome=BeatOutcome.PENDING_GM_REVIEW
        )

    def _url(self, stake):
        return reverse("stake-resolve", kwargs={"pk": stake.pk})

    def test_staff_pick_of_authored_column_succeeds(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            self._url(self.stake),
            {"column": StakeResolutionColumn.WIN, "gm_notes": "Well fought."},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["column"], StakeResolutionColumn.WIN)
        self.assertEqual(resp.data["method"], StakeOutcomeMethod.GM_PICK)
        self.assertEqual(resp.data["gm_notes"], "Well fought.")

    def test_unauthored_column_rejected(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            self._url(self.stake),
            {"column": StakeResolutionColumn.LOSS},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("constrained", str(resp.data))

    def test_unauthored_outcome_key_rejected_under_authored_column(self):
        """A LOSS column authored only as "destroyed" rejects a "captured" pick."""
        StakeResolutionFactory(
            stake=self.stake,
            column=StakeResolutionColumn.LOSS,
            outcome_key="destroyed",
        )
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            self._url(self.stake),
            {"column": StakeResolutionColumn.LOSS, "outcome_key": "captured"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("constrained", str(resp.data))

    def test_second_pick_rejected(self):
        self.client.force_authenticate(user=self.staff)
        first = self.client.post(
            self._url(self.stake), {"column": StakeResolutionColumn.WIN}, format="json"
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.client.post(
            self._url(self.stake), {"column": StakeResolutionColumn.WIN}, format="json"
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already", str(second.data))

    def test_uncompleted_beat_rejected(self):
        _sheet2, beat2, _progress2 = _character_story_beat()
        stake2 = StakeFactory(beat=beat2)
        StakeResolutionFactory(stake=stake2, column=StakeResolutionColumn.WIN)
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            self._url(stake2), {"column": StakeResolutionColumn.WIN}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not completed", str(resp.data))

    def test_player_forbidden(self):
        self.client.force_authenticate(user=self.player)
        resp = self.client.post(
            self._url(self.stake), {"column": StakeResolutionColumn.WIN}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class NoFiatSerializerTests(APITestCase):
    """Pillar 12: the StakeResolution API rejects direct lifecycle writes."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        story = StoryFactory(owners=[cls.staff])
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        cls.beat = BeatFactory(episode=episode)

    def _post_resolution(self, stake, **extra):
        self.client.force_authenticate(user=self.staff)
        payload = {"stake": stake.pk, "column": StakeResolutionColumn.LOSS, **extra}
        return self.client.post(reverse("stakeresolution-list"), payload, format="json")

    def test_lifecycle_payload_rejected_on_personal_jeopardy(self):
        pc_sheet = CharacterSheetFactory()
        stake = StakeFactory(
            beat=self.beat,
            subject_kind=StakeSubjectKind.PERSONAL_JEOPARDY,
            subject_sheet=pc_sheet,
        )
        resp = self._post_resolution(stake, sets_subject_lifecycle=LifecycleState.DEAD)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("pillar 12", str(resp.data))

    def test_lifecycle_payload_rejected_on_player_held_npc_fate(self):
        held_sheet = CharacterSheetFactory()
        entry = RosterEntryFactory(character_sheet=held_sheet)
        RosterTenureFactory(roster_entry=entry, end_date=None)
        stake = StakeFactory(
            beat=self.beat,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=held_sheet,
        )
        resp = self._post_resolution(stake, sets_subject_lifecycle=LifecycleState.CAPTURED)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("pillar 12", str(resp.data))

    def test_lifecycle_payload_allowed_on_unheld_npc_fate(self):
        npc_sheet = CharacterSheetFactory()
        stake = StakeFactory(
            beat=self.beat,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=npc_sheet,
        )
        resp = self._post_resolution(stake, sets_subject_lifecycle=LifecycleState.DEAD)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_item_forfeit_requires_item_stake(self):
        stake = StakeFactory(beat=self.beat)  # CUSTOM, no subject_item
        resp = self._post_resolution(stake, forfeits_subject_item=True)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("forfeits_subject_item", str(resp.data))

    def test_affection_delta_requires_npc_or_faction_subject(self):
        stake = StakeFactory(beat=self.beat)  # CUSTOM, no subject_sheet
        resp = self._post_resolution(stake, subject_standing_delta=-2)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("subject_standing_delta", str(resp.data))

    def test_machine_match_lifecycle_state_rejected_on_non_npc_fate(self):
        """machine_match_lifecycle_state is NPC_FATE-only (#1760), symmetric with
        sets_subject_lifecycle's existing pillar-12 guard — a FACTION/ITEM/CUSTOM
        stake would otherwise silently never match anything.
        """
        stake = StakeFactory(beat=self.beat)  # CUSTOM, no subject_sheet
        resp = self._post_resolution(stake, machine_match_lifecycle_state=LifecycleState.DEAD)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("machine_match_lifecycle_state", str(resp.data))

    def test_machine_match_lifecycle_state_allowed_on_npc_fate(self):
        npc_sheet = CharacterSheetFactory()
        stake = StakeFactory(
            beat=self.beat,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=npc_sheet,
        )
        resp = self._post_resolution(stake, machine_match_lifecycle_state=LifecycleState.DEAD)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)


class WriterTests(EvenniaTestCase):
    """World-state writers applied when a branch fires."""

    @classmethod
    def setUpTestData(cls):
        cls.fail_tier = CheckOutcomeFactory(name="Stake Writer Rout", success_level=-1)

    def test_item_forfeit_soft_deletes_and_logs(self):
        from world.items.constants import OwnershipEventType

        _sheet, beat, progress = _character_story_beat()
        item = ItemInstanceFactory(template=ItemTemplateFactory())
        stake = StakeFactory(beat=beat, subject_kind=StakeSubjectKind.ITEM, subject_item=item)
        StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, forfeits_subject_item=True
        )

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.fail_tier)

        item.refresh_from_db()
        self.assertIsNotNone(item.destroyed_at)
        self.assertTrue(
            item.ownership_events.filter(event_type=OwnershipEventType.TRANSFERRED).exists()
        )

    def test_affection_delta_moves_npc_standing(self):
        sheet, beat, progress = _character_story_beat()
        npc_sheet = CharacterSheetFactory()
        stake = StakeFactory(
            beat=beat, subject_kind=StakeSubjectKind.NPC_FATE, subject_sheet=npc_sheet
        )
        StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, subject_standing_delta=-3
        )

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.fail_tier)

        standing = NPCStanding.objects.get(
            persona=sheet.primary_persona, npc_persona=npc_sheet.primary_persona
        )
        self.assertEqual(standing.affection, -3)

    def test_faction_subject_society_resolution_bumps_society_reputation(self) -> None:
        from world.societies.factories import SocietyFactory
        from world.societies.models import SocietyReputation

        society = SocietyFactory()
        pc_sheet = CharacterSheetFactory()  # post_generation hook auto-creates a PRIMARY persona
        persona = pc_sheet.primary_persona  # PersonaType.PRIMARY -> is_established_or_primary=True

        beat = BeatFactory(predicate_type=BeatPredicateType.GM_MARKED)
        stake = StakeFactory(
            beat=beat,
            subject_kind=StakeSubjectKind.FACTION,
            subject_society=society,
        )
        StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.WIN,
            subject_standing_delta=50,
        )
        story = beat.episode.chapter.story
        progress = StoryProgressFactory(story=story, character_sheet=pc_sheet)

        record_gm_marked_outcome(progress=progress, beat=beat, outcome=BeatOutcome.SUCCESS)

        rep = SocietyReputation.objects.get(persona=persona, society=society)
        self.assertEqual(rep.value, 50)

    def test_lifecycle_write_on_unheld_npc(self):
        _sheet, beat, progress = _character_story_beat()
        npc_sheet = CharacterSheetFactory()
        stake = StakeFactory(
            beat=beat, subject_kind=StakeSubjectKind.NPC_FATE, subject_sheet=npc_sheet
        )
        StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            sets_subject_lifecycle=LifecycleState.DEAD,
        )

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.fail_tier)

        npc_sheet.refresh_from_db()
        self.assertEqual(npc_sheet.lifecycle_state, LifecycleState.DEAD)

    def test_lifecycle_write_refused_on_player_held_sheet(self):
        """Defense in depth: even a mis-authored branch never writes a PC's lifecycle."""
        _sheet, beat, progress = _character_story_beat()
        held_sheet = CharacterSheetFactory()
        entry = RosterEntryFactory(character_sheet=held_sheet)
        RosterTenureFactory(roster_entry=entry, end_date=None)
        stake = StakeFactory(
            beat=beat, subject_kind=StakeSubjectKind.NPC_FATE, subject_sheet=held_sheet
        )
        # Bypass the serializer (factory write) to prove the writer's own gate.
        StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            sets_subject_lifecycle=LifecycleState.DEAD,
        )

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.fail_tier)

        held_sheet.refresh_from_db()
        self.assertEqual(held_sheet.lifecycle_state, LifecycleState.ALIVE)


class StakeRoutingTests(EvenniaTestCase):
    """Stake-level transition routing (TransitionRequiredOutcome.stake)."""

    @classmethod
    def setUpTestData(cls):
        cls.fail_tier = CheckOutcomeFactory(name="Stake Routing Rout", success_level=-1)

    def test_transition_requires_stake_loss(self):
        from world.stories.services.transitions import get_eligible_transitions

        _sheet, beat, progress = _character_story_beat()
        episode = beat.episode
        next_episode = EpisodeFactory(chapter=episode.chapter)
        transition = TransitionFactory(source_episode=episode, target_episode=next_episode)
        stake = StakeFactory(beat=beat)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        TransitionRequiredOutcome.objects.create(
            transition=transition,
            beat=beat,
            required_outcome="",
            stake=stake,
            required_stake_column=StakeResolutionColumn.LOSS,
        )
        progress.current_episode = episode
        progress.save(update_fields=["current_episode"])

        # No StakeOutcome yet -> not eligible.
        self.assertEqual(get_eligible_transitions(progress), [])

        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=self.fail_tier)

        eligible = get_eligible_transitions(progress)
        self.assertEqual([t.pk for t in eligible], [transition.pk])

    def test_clean_enforces_exactly_one_predicate_shape(self):
        from django.core.exceptions import ValidationError

        _sheet, beat, _progress = _character_story_beat()
        other_beat = BeatFactory(episode=beat.episode)
        stake = StakeFactory(beat=beat)
        transition = TransitionFactory(source_episode=beat.episode)

        # Stake set but no column.
        req = TransitionRequiredOutcome(
            transition=transition,
            beat=beat,
            required_outcome="",
            stake=stake,
            required_stake_column="",
        )
        with self.assertRaises(ValidationError):
            req.clean()

        # Stake set with a (misleading, ignored) beat outcome — rejected.
        req_both = TransitionRequiredOutcome(
            transition=transition,
            beat=beat,
            required_outcome=BeatOutcome.FAILURE,
            stake=stake,
            required_stake_column=StakeResolutionColumn.LOSS,
        )
        with self.assertRaises(ValidationError):
            req_both.clean()

        # Stake belongs to a different beat.
        req_wrong_beat = TransitionRequiredOutcome(
            transition=transition,
            beat=other_beat,
            required_outcome="",
            stake=stake,
            required_stake_column=StakeResolutionColumn.LOSS,
        )
        with self.assertRaises(ValidationError):
            req_wrong_beat.clean()

        # Beat-level row with no outcome at all.
        req_empty = TransitionRequiredOutcome(
            transition=transition,
            beat=beat,
            required_outcome="",
        )
        with self.assertRaises(ValidationError):
            req_empty.clean()


def _group_story_pending_staked_beat():
    """A GROUP-scope story with a staked OUTCOME_TIER beat pending GM review."""
    story = StoryFactory(scope=StoryScope.GROUP)
    chapter = ChapterFactory(story=story)
    episode = EpisodeFactory(chapter=chapter)
    gm_table = GMTableFactory()
    progress = GroupStoryProgressFactory(story=story, gm_table=gm_table, current_episode=episode)
    beat = BeatFactory(episode=episode, predicate_type=BeatPredicateType.OUTCOME_TIER)
    stake = StakeFactory(beat=beat)
    consequence = ConsequenceFactory()  # no tier: fires deterministically on pick
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.LEGEND_AWARD,
        legend_base_value=10,
        legend_source_type=LegendSourceTypeFactory(),
        legend_description_template="Group stake won.",
    )
    pool = ConsequencePoolFactory()
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN, consequence_pool=pool)
    record_outcome_tier_completion(
        progress=progress, beat=beat, force_outcome=BeatOutcome.PENDING_GM_REVIEW
    )
    return stake


class GroupScopeGMPickTests(EvenniaTestCase):
    """GROUP-scope constrained picks thread explicit participants (#1770 PR2 review)."""

    @classmethod
    def setUpTestData(cls):
        cls.gm_profile = GMProfileFactory()

    def test_group_pick_with_legend_pool_succeeds_with_participants(self):
        stake = _group_story_pending_staked_beat()
        persona = CharacterSheetFactory().primary_persona

        outcome = resolve_stake_by_gm_pick(
            stake,
            column=StakeResolutionColumn.WIN,
            gm_profile=self.gm_profile,
            participants=[persona],
        )

        self.assertEqual(outcome.method, StakeOutcomeMethod.GM_PICK)
        self.assertTrue(LegendEvent.objects.exists())

    def test_group_pick_affection_delta_reaches_participants(self):
        """The same participant list feeds the subject_standing_delta writer."""
        stake = _group_story_pending_staked_beat()
        npc_sheet = CharacterSheetFactory()
        stake.subject_kind = StakeSubjectKind.NPC_FATE
        stake.subject_sheet = npc_sheet
        stake.save(update_fields=["subject_kind", "subject_sheet"])
        loss = StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, subject_standing_delta=-2
        )
        self.assertIsNotNone(loss)
        persona = CharacterSheetFactory().primary_persona

        resolve_stake_by_gm_pick(
            stake,
            column=StakeResolutionColumn.LOSS,
            gm_profile=self.gm_profile,
            participants=[persona],
        )

        standing = NPCStanding.objects.get(persona=persona, npc_persona=npc_sheet.primary_persona)
        self.assertEqual(standing.affection, -2)


class GroupScopePickEndpointTests(APITestCase):
    """Endpoint-level GROUP-scope pick: participants accepted; guard surfaces as 400."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.stake = _group_story_pending_staked_beat()

    def _url(self):
        return reverse("stake-resolve", kwargs={"pk": self.stake.pk})

    def test_missing_participants_returns_400_not_500(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(self._url(), {"column": StakeResolutionColumn.WIN}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("participants", str(resp.data).lower())
        self.assertFalse(StakeOutcome.objects.filter(stake=self.stake).exists())

    def test_pick_with_participants_succeeds(self):
        persona = CharacterSheetFactory().primary_persona
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            self._url(),
            {"column": StakeResolutionColumn.WIN, "participants": [persona.pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(LegendEvent.objects.exists())


class BulkSaveStakeRoutingTests(APITestCase):
    """save-with-outcomes round-trips stake-level routing rows (#1770 PR2 review).

    Before the fix, a stake-level TransitionRequiredOutcome authored via CRUD
    was silently deleted by any editor bulk-save (delete-and-recreate without
    the stake fields).
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        story = StoryFactory(owners=[cls.staff])
        chapter = ChapterFactory(story=story)
        cls.ep1 = EpisodeFactory(chapter=chapter, order=1)
        cls.ep2 = EpisodeFactory(chapter=chapter, order=2)
        cls.beat = BeatFactory(episode=cls.ep1)
        cls.stake = StakeFactory(beat=cls.beat)

    def _payload(self, existing_id=None):
        return {
            "existing_id": existing_id,
            "source_episode": self.ep1.pk,
            "target_episode": self.ep2.pk,
            "mode": TransitionMode.AUTO,
            "outcomes": [
                {"beat": self.beat.pk, "required_outcome": BeatOutcome.SUCCESS},
                {
                    "beat": self.beat.pk,
                    "stake": self.stake.pk,
                    "required_stake_column": StakeResolutionColumn.LOSS,
                },
            ],
        }

    def test_bulk_save_creates_and_preserves_stake_level_row(self):
        self.client.force_authenticate(user=self.staff)
        url = reverse("transition-save-with-outcomes")

        created = self.client.post(url, self._payload(), format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        transition_id = created.data["id"]
        stake_rows = TransitionRequiredOutcome.objects.filter(
            transition_id=transition_id, stake=self.stake
        )
        self.assertEqual(stake_rows.count(), 1)
        self.assertEqual(stake_rows[0].required_stake_column, StakeResolutionColumn.LOSS)
        self.assertEqual(stake_rows[0].required_outcome, "")

        # Re-save (the delete-and-recreate path) — the stake row must survive.
        updated = self.client.post(url, self._payload(existing_id=transition_id), format="json")
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        stake_rows = TransitionRequiredOutcome.objects.filter(
            transition_id=transition_id, stake=self.stake
        )
        self.assertEqual(stake_rows.count(), 1)
        self.assertEqual(stake_rows[0].required_stake_column, StakeResolutionColumn.LOSS)

    def test_bulk_save_rejects_stake_row_with_beat_outcome(self):
        self.client.force_authenticate(user=self.staff)
        payload = self._payload()
        payload["outcomes"][1]["required_outcome"] = BeatOutcome.FAILURE
        resp = self.client.post(reverse("transition-save-with-outcomes"), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
