"""Tests for world.stories.services.scheduling — maybe_create_session_request.

Wave 7, Task 7.2.
"""

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    SessionRequestStatus,
    TransitionMode,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeProgressionRequirementFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
)
from world.stories.models import SessionRequest
from world.stories.services.beats import (
    record_aggregate_contribution,
    record_gm_marked_outcome,
)
from world.stories.services.scheduling import maybe_create_session_request


class MaybeCreateSessionRequestDirectTests(EvenniaTestCase):
    """Unit tests for maybe_create_session_request called directly."""

    def _make_progress_with_gm_beat(self):
        """Return a StoryProgress whose current episode has an eligible transition
        gated by a GM_MARKED beat that is still UNSATISFIED."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        episode = EpisodeFactory(chapter=chapter, order=1)
        target = EpisodeFactory(chapter=chapter, order=2)

        # Progression requirement: GM_MARKED beat must be SUCCESS to advance.
        gm_beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.SUCCESS,
        )
        EpisodeProgressionRequirementFactory(
            episode=episode, beat=gm_beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionFactory(source_episode=episode, target_episode=target, mode=TransitionMode.AUTO)

        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)
        return progress, episode

    def test_no_session_request_when_no_current_episode(self):
        """Returns None when progress.current_episode is None."""
        story = StoryFactory()
        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=None)

        result = maybe_create_session_request(progress)
        self.assertIsNone(result)

    def test_no_session_request_when_progression_not_met(self):
        """Returns None when progression requirements are unmet (episode not ready)."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        episode = EpisodeFactory(chapter=chapter, order=1)

        # Progression gate: beat is still UNSATISFIED, requirement needs SUCCESS.
        gm_beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,  # NOT met
        )
        EpisodeProgressionRequirementFactory(
            episode=episode, beat=gm_beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionFactory(source_episode=episode, target_episode=EpisodeFactory(chapter=chapter))

        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)

        result = maybe_create_session_request(progress)
        self.assertIsNone(result)

    def test_no_session_request_when_no_gm_involvement_needed(self):
        """Returns None when all transitions are AUTO and no GM_MARKED beats are UNSATISFIED."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        episode = EpisodeFactory(chapter=chapter, order=1)
        target = EpisodeFactory(chapter=chapter, order=2)

        # No progression requirements, AUTO transition, no GM_MARKED beats.
        TransitionFactory(source_episode=episode, target_episode=target, mode=TransitionMode.AUTO)

        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)

        result = maybe_create_session_request(progress)
        self.assertIsNone(result)
        self.assertEqual(SessionRequest.objects.filter(episode=episode).count(), 0)

    def test_session_request_created_when_gm_choice_transition(self):
        """Creates OPEN SessionRequest when an eligible transition is GM_CHOICE."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        episode = EpisodeFactory(chapter=chapter, order=1)
        target = EpisodeFactory(chapter=chapter, order=2)

        # GM_CHOICE transition — eligible immediately (no progression gates).
        TransitionFactory(
            source_episode=episode, target_episode=target, mode=TransitionMode.GM_CHOICE
        )

        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)

        result = maybe_create_session_request(progress)

        self.assertIsNotNone(result)
        self.assertEqual(result.status, SessionRequestStatus.OPEN)
        self.assertEqual(result.episode_id, episode.pk)

    def test_session_request_created_when_episode_has_unsatisfied_gm_beat(self):
        """Creates OPEN SessionRequest when the episode has an UNSATISFIED GM_MARKED beat,
        even though the progression gate is met (beat was already SUCCESS elsewhere)."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        episode = EpisodeFactory(chapter=chapter, order=1)
        target = EpisodeFactory(chapter=chapter, order=2)

        # A separate gate beat that IS satisfied.
        gate_beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.SUCCESS,
        )
        EpisodeProgressionRequirementFactory(
            episode=episode, beat=gate_beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionFactory(source_episode=episode, target_episode=target, mode=TransitionMode.AUTO)

        # A second GM_MARKED beat that is still UNSATISFIED — needs a GM session.
        BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
        )

        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)

        result = maybe_create_session_request(progress)

        self.assertIsNotNone(result)
        self.assertEqual(result.status, SessionRequestStatus.OPEN)

    def test_idempotent_open_request_not_duplicated(self):
        """Calling maybe_create_session_request twice returns the same request."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        episode = EpisodeFactory(chapter=chapter, order=1)
        target = EpisodeFactory(chapter=chapter, order=2)

        TransitionFactory(
            source_episode=episode, target_episode=target, mode=TransitionMode.GM_CHOICE
        )

        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)

        result1 = maybe_create_session_request(progress)
        result2 = maybe_create_session_request(progress)

        self.assertEqual(result1.pk, result2.pk)
        self.assertEqual(SessionRequest.objects.filter(episode=episode).count(), 1)

    def test_idempotent_scheduled_request_not_duplicated(self):
        """An already-SCHEDULED request is returned without creating a new OPEN one."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        episode = EpisodeFactory(chapter=chapter, order=1)
        target = EpisodeFactory(chapter=chapter, order=2)

        TransitionFactory(
            source_episode=episode, target_episode=target, mode=TransitionMode.GM_CHOICE
        )

        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)

        # Pre-create a SCHEDULED request.
        existing = SessionRequest.objects.create(
            episode=episode, status=SessionRequestStatus.SCHEDULED
        )

        result = maybe_create_session_request(progress)

        self.assertEqual(result.pk, existing.pk)
        self.assertEqual(SessionRequest.objects.filter(episode=episode).count(), 1)


class SessionRequestAutoCreatedFromBeatsTests(EvenniaTestCase):
    """Integration tests: verify that beat write-path services trigger SessionRequest creation."""

    def test_session_request_created_after_gm_marked_outcome(self):
        """record_gm_marked_outcome triggers SessionRequest creation when episode becomes ready."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        episode = EpisodeFactory(chapter=chapter, order=1)
        target = EpisodeFactory(chapter=chapter, order=2)

        gm_beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
        )
        EpisodeProgressionRequirementFactory(
            episode=episode, beat=gm_beat, required_outcome=BeatOutcome.SUCCESS
        )
        # GM_CHOICE transition — once the gate is met, a GM must choose the path.
        TransitionFactory(
            source_episode=episode, target_episode=target, mode=TransitionMode.GM_CHOICE
        )

        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)

        self.assertEqual(SessionRequest.objects.filter(episode=episode).count(), 0)

        record_gm_marked_outcome(
            progress=progress, beat=gm_beat, outcome=BeatOutcome.SUCCESS, gm_notes="done"
        )

        self.assertEqual(SessionRequest.objects.filter(episode=episode).count(), 1)
        sr = SessionRequest.objects.get(episode=episode)
        self.assertEqual(sr.status, SessionRequestStatus.OPEN)

    def test_session_request_created_after_aggregate_threshold_crossed(self):
        """record_aggregate_contribution triggers SessionRequest creation when threshold
        is crossed and the episode has a GM_CHOICE transition."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        episode = EpisodeFactory(chapter=chapter, order=1)
        target = EpisodeFactory(chapter=chapter, order=2)

        # Aggregate beat: threshold=10, requires SUCCESS to progress.
        agg_beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=10,
            outcome=BeatOutcome.UNSATISFIED,
        )
        EpisodeProgressionRequirementFactory(
            episode=episode, beat=agg_beat, required_outcome=BeatOutcome.SUCCESS
        )
        # GM_CHOICE transition: once threshold met, GM must pick the path.
        TransitionFactory(
            source_episode=episode, target_episode=target, mode=TransitionMode.GM_CHOICE
        )

        sheet = CharacterSheetFactory()
        # Active progress for the story so maybe_create_session_request can find it.
        StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)

        self.assertEqual(SessionRequest.objects.filter(episode=episode).count(), 0)

        record_aggregate_contribution(
            beat=agg_beat, character_sheet=sheet, points=15, source_note="siege victory"
        )

        self.assertEqual(SessionRequest.objects.filter(episode=episode).count(), 1)
        sr = SessionRequest.objects.get(episode=episode)
        self.assertEqual(sr.status, SessionRequestStatus.OPEN)

    def test_session_request_not_created_when_aggregate_threshold_not_met(self):
        """record_aggregate_contribution does NOT create a SessionRequest when threshold
        has not yet been crossed."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        episode = EpisodeFactory(chapter=chapter, order=1)
        target = EpisodeFactory(chapter=chapter, order=2)

        agg_beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=100,  # high threshold
            outcome=BeatOutcome.UNSATISFIED,
        )
        EpisodeProgressionRequirementFactory(
            episode=episode, beat=agg_beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionFactory(
            source_episode=episode, target_episode=target, mode=TransitionMode.GM_CHOICE
        )

        sheet = CharacterSheetFactory()
        StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)

        record_aggregate_contribution(
            beat=agg_beat, character_sheet=sheet, points=5, source_note="small contribution"
        )

        self.assertEqual(SessionRequest.objects.filter(episode=episode).count(), 0)

    def test_session_request_idempotent_on_repeat_gm_mark(self):
        """Calling record_gm_marked_outcome (or evaluate_auto_beats) twice does not
        create duplicate SessionRequest rows."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story, order=1)
        episode = EpisodeFactory(chapter=chapter, order=1)
        target = EpisodeFactory(chapter=chapter, order=2)

        gm_beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
        )
        EpisodeProgressionRequirementFactory(
            episode=episode, beat=gm_beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionFactory(
            source_episode=episode, target_episode=target, mode=TransitionMode.GM_CHOICE
        )

        sheet = CharacterSheetFactory()
        progress = StoryProgressFactory(story=story, character_sheet=sheet, current_episode=episode)

        record_gm_marked_outcome(
            progress=progress, beat=gm_beat, outcome=BeatOutcome.SUCCESS, gm_notes="first"
        )
        # Call maybe_create again directly to simulate a second write-path call.
        maybe_create_session_request(progress)

        self.assertEqual(SessionRequest.objects.filter(episode=episode).count(), 1)
