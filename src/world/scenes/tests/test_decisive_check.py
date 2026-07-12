"""Tests for the scene decisive-check marker (#1748).

Covers: marker creation, cancellation, the maybe_fire hook, guard conditions,
and the E2E flow from marker creation through check-outcome propagation to
beat completion.
"""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import DecisiveCheckMarkerStatus
from world.scenes.decisive_check_services import (
    DecisiveCheckError,
    cancel_decisive_check_marker,
    create_decisive_check_marker,
    get_pending_marker,
    maybe_fire_decisive_check,
)
from world.scenes.factories import SceneFactory
from world.stories.constants import BeatOutcome, BeatPredicateType, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeSceneFactory,
    StoryFactory,
)
from world.stories.models import BeatCompletion
from world.traits.factories import CheckOutcomeFactory


class DecisiveCheckMarkerCreationTests(EvenniaTestCase):
    """Tests for DecisiveCheckMarker creation and validation."""

    def setUp(self) -> None:
        super().setUp()
        self.scene = SceneFactory()
        self.story = StoryFactory(scope=StoryScope.GLOBAL)
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter)
        # Link the episode to the scene via EpisodeScene
        EpisodeSceneFactory(episode=self.episode, scene=self.scene)
        self.beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )

    def test_create_marker_sets_pending_status(self) -> None:
        """Creating a marker sets it to PENDING."""
        marker = create_decisive_check_marker(scene=self.scene, beat=self.beat)
        self.assertEqual(marker.status, DecisiveCheckMarkerStatus.PENDING)
        self.assertEqual(marker.beat, self.beat)
        self.assertEqual(marker.scene, self.scene)
        self.assertIsNone(marker.resolved_outcome_tier)

    def test_create_marker_rejects_non_outcome_tier_beat(self) -> None:
        """A GM_MARKED beat cannot be used (it lacks the tier-graded path)."""
        gm_beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
        )
        with self.assertRaises(DecisiveCheckError) as cm:
            create_decisive_check_marker(scene=self.scene, beat=gm_beat)
        self.assertIn("not OUTCOME_TIER", cm.exception.user_message)

    def test_create_marker_rejects_already_resolved_beat(self) -> None:
        """An already-resolved beat cannot be marked as decisive."""
        resolved_beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.SUCCESS,
        )
        with self.assertRaises(DecisiveCheckError) as cm:
            create_decisive_check_marker(scene=self.scene, beat=resolved_beat)
        self.assertIn("already resolved", cm.exception.user_message)

    def test_create_marker_rejects_unlinked_beat(self) -> None:
        """A beat not linked to the scene via EpisodeScene is rejected."""
        other_episode = EpisodeFactory(chapter=self.chapter)
        unlinked_beat = BeatFactory(
            episode=other_episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        with self.assertRaises(DecisiveCheckError) as cm:
            create_decisive_check_marker(scene=self.scene, beat=unlinked_beat)
        self.assertIn("not linked", cm.exception.user_message)

    def test_create_marker_rejects_duplicate_pending(self) -> None:
        """Only one PENDING marker per scene at a time."""
        create_decisive_check_marker(scene=self.scene, beat=self.beat)
        other_beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        with self.assertRaises(DecisiveCheckError) as cm:
            create_decisive_check_marker(scene=self.scene, beat=other_beat)
        self.assertIn("already has a pending", cm.exception.user_message)

    def test_get_pending_marker_returns_none_when_empty(self) -> None:
        """get_pending_marker returns None when no marker exists."""
        self.assertIsNone(get_pending_marker(self.scene))


class DecisiveCheckMarkerCancelTests(EvenniaTestCase):
    """Tests for DecisiveCheckMarker cancellation."""

    def setUp(self) -> None:
        super().setUp()
        self.scene = SceneFactory()
        self.story = StoryFactory(scope=StoryScope.GLOBAL)
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter)
        EpisodeSceneFactory(episode=self.episode, scene=self.scene)
        self.beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        self.marker = create_decisive_check_marker(scene=self.scene, beat=self.beat)

    def test_cancel_sets_cancelled_status(self) -> None:
        """Cancelling a PENDING marker sets it to CANCELLED."""
        cancel_decisive_check_marker(marker=self.marker)
        self.marker.refresh_from_db()
        self.assertEqual(self.marker.status, DecisiveCheckMarkerStatus.CANCELLED)

    def test_cancel_rejects_resolved_marker(self) -> None:
        """A RESOLVED marker cannot be cancelled."""
        self.marker.status = DecisiveCheckMarkerStatus.RESOLVED
        self.marker.save(update_fields=["status"])
        with self.assertRaises(DecisiveCheckError):
            cancel_decisive_check_marker(marker=self.marker)

    def test_cancel_allows_new_marker_after(self) -> None:
        """After cancelling, a new marker can be created on the scene."""
        cancel_decisive_check_marker(marker=self.marker)
        new_marker = create_decisive_check_marker(scene=self.scene, beat=self.beat)
        self.assertEqual(new_marker.status, DecisiveCheckMarkerStatus.PENDING)


class MaybeFireDecisiveCheckTests(EvenniaTestCase):
    """Tests for the maybe_fire_decisive_check hook."""

    def setUp(self) -> None:
        super().setUp()
        self.scene = SceneFactory()
        self.story = StoryFactory(scope=StoryScope.GLOBAL)
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter)
        EpisodeSceneFactory(episode=self.episode, scene=self.scene)
        self.beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        # Create a GLOBAL story progress so record_outcome_tier_completion can find it
        from world.stories.models import GlobalStoryProgress

        GlobalStoryProgress.objects.create(story=self.story, is_active=True)
        self.sheet = CharacterSheetFactory()
        # A positive success_level CheckOutcome → SUCCESS
        self.success_outcome = CheckOutcomeFactory(success_level=5)
        # A negative success_level CheckOutcome → FAILURE
        self.failure_outcome = CheckOutcomeFactory(success_level=-3)

    def test_fire_with_no_marker_returns_none(self) -> None:
        """maybe_fire returns None when no pending marker exists."""
        result = maybe_fire_decisive_check(
            scene=self.scene,
            check_outcome=self.success_outcome,
            initiator_sheet=self.sheet,
        )
        self.assertIsNone(result)

    def test_fire_with_none_outcome_returns_none(self) -> None:
        """maybe_fire returns None when check_outcome is None."""
        create_decisive_check_marker(scene=self.scene, beat=self.beat)
        result = maybe_fire_decisive_check(
            scene=self.scene,
            check_outcome=None,
            initiator_sheet=self.sheet,
        )
        self.assertIsNone(result)
        # Marker stays PENDING
        marker = get_pending_marker(self.scene)
        self.assertIsNotNone(marker)
        self.assertEqual(marker.status, DecisiveCheckMarkerStatus.PENDING)

    def test_fire_resolves_beat_on_success_outcome(self) -> None:
        """A positive success_level CheckOutcome resolves the beat to SUCCESS."""
        marker = create_decisive_check_marker(scene=self.scene, beat=self.beat)
        result = maybe_fire_decisive_check(
            scene=self.scene,
            check_outcome=self.success_outcome,
            initiator_sheet=self.sheet,
        )
        self.assertIsNotNone(result)
        marker.refresh_from_db()
        self.assertEqual(marker.status, DecisiveCheckMarkerStatus.RESOLVED)
        self.assertEqual(marker.resolved_outcome_tier, self.success_outcome)
        self.assertIsNotNone(marker.resolved_at)
        # Beat flipped to SUCCESS
        self.beat.refresh_from_db()
        self.assertEqual(self.beat.outcome, BeatOutcome.SUCCESS)
        # BeatCompletion created with correct outcome_tier
        completion = BeatCompletion.objects.get(beat=self.beat)
        self.assertEqual(completion.outcome, BeatOutcome.SUCCESS)
        self.assertEqual(completion.outcome_tier, self.success_outcome)

    def test_fire_resolves_beat_on_failure_outcome(self) -> None:
        """A negative success_level CheckOutcome resolves the beat to FAILURE."""
        create_decisive_check_marker(scene=self.scene, beat=self.beat)
        maybe_fire_decisive_check(
            scene=self.scene,
            check_outcome=self.failure_outcome,
            initiator_sheet=self.sheet,
        )
        self.beat.refresh_from_db()
        self.assertEqual(self.beat.outcome, BeatOutcome.FAILURE)
        completion = BeatCompletion.objects.get(beat=self.beat)
        self.assertEqual(completion.outcome, BeatOutcome.FAILURE)
        self.assertEqual(completion.outcome_tier, self.failure_outcome)

    def test_fire_marks_marker_resolved(self) -> None:
        """After firing, the marker is RESOLVED with the outcome_tier set."""
        marker = create_decisive_check_marker(scene=self.scene, beat=self.beat)
        maybe_fire_decisive_check(
            scene=self.scene,
            check_outcome=self.success_outcome,
            initiator_sheet=self.sheet,
        )
        marker.refresh_from_db()
        self.assertEqual(marker.status, DecisiveCheckMarkerStatus.RESOLVED)
        self.assertEqual(marker.resolved_outcome_tier, self.success_outcome)

    def test_fire_with_no_progress_returns_none(self) -> None:
        """When no story progress exists, the marker stays PENDING."""
        # Create a separate story/episode/beat with no progress
        no_progress_story = StoryFactory(scope=StoryScope.GLOBAL)
        no_progress_chapter = ChapterFactory(story=no_progress_story)
        no_progress_episode = EpisodeFactory(chapter=no_progress_chapter)
        EpisodeSceneFactory(episode=no_progress_episode, scene=self.scene)
        no_progress_beat = BeatFactory(
            episode=no_progress_episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        # No GlobalStoryProgress created for this story
        marker = create_decisive_check_marker(scene=self.scene, beat=no_progress_beat)
        result = maybe_fire_decisive_check(
            scene=self.scene,
            check_outcome=self.success_outcome,
            initiator_sheet=self.sheet,
        )
        self.assertIsNone(result)
        marker.refresh_from_db()
        self.assertEqual(marker.status, DecisiveCheckMarkerStatus.PENDING)

    def test_fire_only_fires_once(self) -> None:
        """After the marker fires, a second check does not re-resolve."""
        create_decisive_check_marker(scene=self.scene, beat=self.beat)
        maybe_fire_decisive_check(
            scene=self.scene,
            check_outcome=self.success_outcome,
            initiator_sheet=self.sheet,
        )
        # Second call — no PENDING marker anymore
        result = maybe_fire_decisive_check(
            scene=self.scene,
            check_outcome=self.success_outcome,
            initiator_sheet=self.sheet,
        )
        self.assertIsNone(result)
        # Only one BeatCompletion
        self.assertEqual(BeatCompletion.objects.filter(beat=self.beat).count(), 1)
