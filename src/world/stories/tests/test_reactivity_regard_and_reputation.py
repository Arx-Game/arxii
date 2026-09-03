"""Regard events and reputation bumps re-evaluate open beats (#3570).

``record_npc_regard_event`` (npc_services.regard) and
``bump_society_reputation`` / ``bump_organization_reputation``
(societies.renown) each call ``on_character_state_changed`` after their
write commits, so a beat gated on NPC_REGARD_AT_LEAST or
FACTION_STANDING_AT_LEAST can flip in the same request that moved the
underlying value, no login or separate re-evaluation pass needed. The
regard writer's call sits inside its existing ``transaction.atomic()``
block, so a rollback of the triggering write discards the flip too.
"""

from django.db import transaction
from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.constants import NpcRegardEventReason
from world.npc_services.models import NpcRegard
from world.npc_services.regard import record_npc_regard_event
from world.societies.factories import OrganizationFactory, SocietyFactory
from world.societies.models import SocietyReputation
from world.societies.renown import bump_organization_reputation, bump_society_reputation
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    StakeResolutionColumn,
    StakeSubjectKind,
)
from world.stories.factories import BeatFactory, StakeFactory, StakeResolutionFactory
from world.stories.models import BeatCompletion
from world.stories.services.beats import record_outcome_tier_completion
from world.stories.tests.test_services_stake_resolution import _character_story_beat
from world.traits.factories import CheckOutcomeFactory


def _open_progress_on(progress, episode):
    """Point ``progress`` at ``episode`` so evaluate_auto_beats considers its beats.

    ``_character_story_beat`` leaves ``current_episode`` at its factory default
    of None (evaluate_auto_beats no-ops on that); every test below needs the
    trigger beat's episode open so the gated sibling beat gets evaluated.
    """
    progress.current_episode = episode
    progress.save(update_fields=["current_episode"])
    return progress


class RegardReactivityTests(EvenniaTestCase):
    """record_npc_regard_event re-evaluates NPC_REGARD_AT_LEAST beats."""

    def setUp(self) -> None:
        super().setUp()
        self.sheet, self.trigger_beat, self.progress = _character_story_beat()
        _open_progress_on(self.progress, self.trigger_beat.episode)
        self.npc_sheet = CharacterSheetFactory()
        self.gated = BeatFactory(
            episode=self.trigger_beat.episode,
            predicate_type=BeatPredicateType.NPC_REGARD_AT_LEAST,
            required_npc_sheet=self.npc_sheet,
            required_standing=5,
        )

    def test_regard_event_flips_the_gated_beat_in_the_same_request(self) -> None:
        record_npc_regard_event(
            holder_persona=self.npc_sheet.primary_persona,
            target=self.sheet.primary_persona,
            amount=5,
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
        )
        self.gated.refresh_from_db()
        self.assertEqual(self.gated.outcome, BeatOutcome.SUCCESS)

    def test_regard_below_threshold_leaves_it_waiting(self) -> None:
        record_npc_regard_event(
            holder_persona=self.npc_sheet.primary_persona,
            target=self.sheet.primary_persona,
            amount=-3,
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
        )
        self.gated.refresh_from_db()
        self.assertEqual(self.gated.outcome, BeatOutcome.UNSATISFIED)

    def test_stake_loss_then_win_flips_through_the_writer(self) -> None:
        # LOSS branch on the trigger beat lowers regard (-5, stays below the
        # gated beat's threshold of 5); WIN branch on a second beat raises it
        # (+12): the gated beat flips inside the second completion's pool fire,
        # not at login.
        fail_tier = CheckOutcomeFactory(name="Regard Reactivity Rout", success_level=-1)
        win_tier = CheckOutcomeFactory(name="Regard Reactivity Triumph", success_level=3)

        stake = StakeFactory(
            beat=self.trigger_beat,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=self.npc_sheet,
        )
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS, npc_regard_delta=-5)
        record_outcome_tier_completion(
            progress=self.progress, beat=self.trigger_beat, outcome_tier=fail_tier
        )
        self.gated.refresh_from_db()
        self.assertEqual(self.gated.outcome, BeatOutcome.UNSATISFIED)

        second = BeatFactory(
            episode=self.trigger_beat.episode, predicate_type=BeatPredicateType.OUTCOME_TIER
        )
        stake2 = StakeFactory(
            beat=second, subject_kind=StakeSubjectKind.NPC_FATE, subject_sheet=self.npc_sheet
        )
        StakeResolutionFactory(stake=stake2, column=StakeResolutionColumn.WIN, npc_regard_delta=12)
        record_outcome_tier_completion(progress=self.progress, beat=second, outcome_tier=win_tier)
        self.gated.refresh_from_db()
        self.assertEqual(self.gated.outcome, BeatOutcome.SUCCESS)

    def test_rollback_discards_the_flip(self) -> None:
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                record_npc_regard_event(
                    holder_persona=self.npc_sheet.primary_persona,
                    target=self.sheet.primary_persona,
                    amount=5,
                    reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
                )
                msg = "boom"
                raise RuntimeError(msg)

        # The evaluator's beat.save() mutated the identity-mapped instance
        # in place before the rollback; a plain refresh_from_db() on a
        # SharedMemoryModel that's still cache-resident returns the SAME
        # (stale) instance rather than re-querying (idmapper's from_db()
        # short-circuits to the cached object). flush_from_cache(force=True)
        # evicts it so refresh_from_db() genuinely re-fetches the rolled-back
        # DB row.
        self.gated.flush_from_cache(force=True)
        self.gated.refresh_from_db()
        self.assertEqual(self.gated.outcome, BeatOutcome.UNSATISFIED)
        self.assertFalse(
            NpcRegard.objects.filter(
                holder_persona=self.npc_sheet.primary_persona,
                target_persona=self.sheet.primary_persona,
            ).exists()
        )


class ReputationReactivityTests(EvenniaTestCase):
    """The reputation bumps re-evaluate FACTION_STANDING_AT_LEAST beats."""

    def test_society_bump_flips_a_faction_beat_without_a_login(self) -> None:
        sheet, trigger_beat, progress = _character_story_beat()
        _open_progress_on(progress, trigger_beat.episode)
        society = SocietyFactory()
        gated = BeatFactory(
            episode=trigger_beat.episode,
            predicate_type=BeatPredicateType.FACTION_STANDING_AT_LEAST,
            required_society=society,
            required_standing=100,
        )

        bump_society_reputation(sheet.primary_persona, society, 150)

        gated.refresh_from_db()
        self.assertEqual(gated.outcome, BeatOutcome.SUCCESS)

    def test_organization_bump_flips_an_organization_beat(self) -> None:
        sheet, trigger_beat, progress = _character_story_beat()
        _open_progress_on(progress, trigger_beat.episode)
        organization = OrganizationFactory()
        gated = BeatFactory(
            episode=trigger_beat.episode,
            predicate_type=BeatPredicateType.FACTION_STANDING_AT_LEAST,
            required_organization=organization,
            required_standing=100,
        )

        bump_organization_reputation(sheet.primary_persona, organization, 150)

        gated.refresh_from_db()
        self.assertEqual(gated.outcome, BeatOutcome.SUCCESS)

    def test_zero_delta_does_not_evaluate(self) -> None:
        sheet, trigger_beat, progress = _character_story_beat()
        _open_progress_on(progress, trigger_beat.episode)
        society = SocietyFactory()
        # Pre-seed a standing that already clears the gate, so a spurious
        # evaluation would be visible: if the zero-delta bump ran
        # on_character_state_changed anyway, this beat would flip to SUCCESS.
        SocietyReputation.objects.create(persona=sheet.primary_persona, society=society, value=200)
        gated = BeatFactory(
            episode=trigger_beat.episode,
            predicate_type=BeatPredicateType.FACTION_STANDING_AT_LEAST,
            required_society=society,
            required_standing=100,
        )

        result = bump_society_reputation(sheet.primary_persona, society, 0)

        self.assertIsNone(result)
        gated.refresh_from_db()
        self.assertEqual(gated.outcome, BeatOutcome.UNSATISFIED)
        self.assertFalse(BeatCompletion.objects.filter(beat=gated).exists())
