"""Tests for ``on_mission_complete_for_beat`` — the mission→Beat seam.

Phase 5b.3 landed the trigger-record shape; this module now also verifies
that the linked ``Beat`` is completed when a beat-bound instance terminates.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.missions.factories import (
    MissionInstanceFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.services import beat as beat_service, on_mission_complete_for_beat
from world.stories.constants import BeatOutcome, BeatPredicateType, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import BeatCompletion
from world.traits.factories import CheckOutcomeFactory


class OnMissionCompleteForBeatTests(TestCase):
    """Trigger-record shape: free → None; beat-bound → record."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(name="beat-svc-tmpl")

    def setUp(self) -> None:
        beat_service.clear_triggers()

    def test_free_mission_returns_none_and_records_nothing(self) -> None:
        instance = MissionInstanceFactory(template=self.template, source_beat=None)
        self.assertIsNone(instance.source_beat_id)

        result = on_mission_complete_for_beat(instance)

        self.assertIsNone(result)
        self.assertEqual(beat_service.get_triggers(), ())

    def test_beat_bound_mission_returns_record_and_logs_trigger(self) -> None:
        beat = BeatFactory()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)

        result = on_mission_complete_for_beat(instance)

        self.assertIsNotNone(result)
        self.assertEqual(result.instance_pk, instance.pk)
        self.assertEqual(result.beat_pk, beat.pk)
        self.assertIsNotNone(result.triggered_at)

        triggers = beat_service.get_triggers()
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0], result)

    def test_clear_triggers_resets_state(self) -> None:
        beat = BeatFactory()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)

        on_mission_complete_for_beat(instance)
        self.assertEqual(len(beat_service.get_triggers()), 1)

        beat_service.clear_triggers()
        self.assertEqual(beat_service.get_triggers(), ())

    def test_double_call_records_two_triggers_not_idempotent(self) -> None:
        # The trigger log is append-only (observability). The beat-completion
        # guard prevents a double-completion (see MissionBeatCompletionTests).
        beat = BeatFactory()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)

        first = on_mission_complete_for_beat(instance)
        second = on_mission_complete_for_beat(instance)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(len(beat_service.get_triggers()), 2)


class MissionBeatCompletionTests(TestCase):
    """on_mission_complete_for_beat completes the linked Beat."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(name="beat-completion-tmpl")
        cls.sheet = CharacterSheetFactory()
        cls.story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=cls.sheet)
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)

    def setUp(self) -> None:
        beat_service.clear_triggers()

    def _make_progress(self):
        return StoryProgressFactory(
            story=self.story, character_sheet=self.sheet, current_episode=self.episode
        )

    def test_check_terminal_completes_outcome_tier_beat(self) -> None:
        """A graded-tier route completes an OUTCOME_TIER beat via record_outcome_tier_completion."""
        tier = CheckOutcomeFactory(name="Victory", success_level=4)
        beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
        )
        self._make_progress()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)
        route = MissionOptionRouteFactory(outcome_tier=tier, target_node=None)

        on_mission_complete_for_beat(instance, route=route)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        completion = BeatCompletion.objects.get(beat=beat)
        self.assertEqual(completion.outcome_tier, tier)

    def test_failure_tier_completes_outcome_tier_beat_as_failure(self) -> None:
        """A negative success_level tier resolves FAILURE."""
        tier = CheckOutcomeFactory(name="Defeat", success_level=-3)
        beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
        )
        self._make_progress()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)
        route = MissionOptionRouteFactory(outcome_tier=tier, target_node=None)

        on_mission_complete_for_beat(instance, route=route)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.FAILURE)
        completion = BeatCompletion.objects.get(beat=beat)
        self.assertEqual(completion.outcome_tier, tier)

    def test_branch_terminal_completes_gm_marked_beat_as_success(self) -> None:
        """A no-tier route (BRANCH) completes a GM_MARKED beat as SUCCESS."""
        beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.GM_MARKED,
        )
        self._make_progress()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)
        route = MissionOptionRouteFactory(outcome_tier=None, target_node=None)

        on_mission_complete_for_beat(instance, route=route)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        self.assertTrue(BeatCompletion.objects.filter(beat=beat).exists())

    def test_branch_terminal_with_none_route_completes_gm_marked_beat(self) -> None:
        """route=None (branch_target-only terminal) still completes as SUCCESS."""
        beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.GM_MARKED,
        )
        self._make_progress()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)

        on_mission_complete_for_beat(instance, route=None)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_skips_when_no_progress(self) -> None:
        """No StoryProgress → no BeatCompletion, no error."""
        tier = CheckOutcomeFactory(success_level=3)
        beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
        )
        # No StoryProgress created.
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)
        route = MissionOptionRouteFactory(outcome_tier=tier, target_node=None)

        on_mission_complete_for_beat(instance, route=route)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
        self.assertFalse(BeatCompletion.objects.filter(beat=beat).exists())

    def test_skips_when_beat_already_resolved(self) -> None:
        """An already-resolved beat is not double-completed."""
        tier = CheckOutcomeFactory(success_level=4)
        beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.SUCCESS,
        )
        self._make_progress()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)
        route = MissionOptionRouteFactory(outcome_tier=tier, target_node=None)

        on_mission_complete_for_beat(instance, route=route)

        # No new BeatCompletion created (beat was already SUCCESS).
        self.assertEqual(BeatCompletion.objects.filter(beat=beat).count(), 0)

    def test_predicate_mismatch_logged_not_raised(self) -> None:
        """GM_MARKED beat + graded route → ValueError caught, no crash."""
        tier = CheckOutcomeFactory(success_level=4)
        beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.GM_MARKED,
        )
        self._make_progress()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)
        route = MissionOptionRouteFactory(outcome_tier=tier, target_node=None)

        # Must not raise.
        on_mission_complete_for_beat(instance, route=route)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_double_call_completes_beat_only_once(self) -> None:
        """The trigger log records two entries, but the beat completes once."""
        tier = CheckOutcomeFactory(success_level=4)
        beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
        )
        self._make_progress()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)
        route = MissionOptionRouteFactory(outcome_tier=tier, target_node=None)

        on_mission_complete_for_beat(instance, route=route)
        on_mission_complete_for_beat(instance, route=route)

        # Two trigger records (append-only log).
        self.assertEqual(len(beat_service.get_triggers()), 2)
        # But only one BeatCompletion.
        self.assertEqual(BeatCompletion.objects.filter(beat=beat).count(), 1)
