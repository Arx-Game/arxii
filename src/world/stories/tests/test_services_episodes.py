"""Tests for world.stories.services.episodes."""

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory
from world.stories.constants import BeatOutcome, EraStatus
from world.stories.exceptions import (
    NoEligibleTransitionError,
    ProgressionRequirementNotMetError,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeProgressionRequirementFactory,
    EraFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.models import EpisodeResolution
from world.stories.services.episodes import resolve_episode


class ResolveEpisodeTests(EvenniaTestCase):
    """Tests for resolve_episode."""

    def _make_story_structure(self):
        """Create story → chapter → two episodes, return (source, target)."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story)
        source = EpisodeFactory(chapter=chapter)
        target = EpisodeFactory(chapter=chapter)
        return source, target

    def _make_progress(self, episode):
        sheet = CharacterSheetFactory()
        return StoryProgressFactory(character_sheet=sheet, current_episode=episode)

    # ------------------------------------------------------------------
    # Happy paths
    # ------------------------------------------------------------------

    def test_single_eligible_transition_fires_and_advances_progress(self):
        """A single eligible transition advances progress to its target."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)
        transition = TransitionFactory(
            source_episode=source,
            target_episode=target,
        )

        resolution = resolve_episode(progress=progress)

        self.assertIsInstance(resolution, EpisodeResolution)
        self.assertEqual(resolution.chosen_transition, transition)
        self.assertEqual(resolution.episode, source)

        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, target)

    def test_null_target_parks_progress_at_frontier(self):
        """Transition with target_episode=None advances to None (frontier)."""
        source, _unused = self._make_story_structure()
        progress = self._make_progress(source)
        frontier_transition = TransitionFactory(
            source_episode=source,
            target_episode=None,
        )

        resolution = resolve_episode(progress=progress)

        progress.refresh_from_db()
        self.assertIsNone(progress.current_episode)
        self.assertEqual(resolution.chosen_transition, frontier_transition)

    def test_episode_resolution_row_is_created(self):
        """EpisodeResolution DB row is persisted."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)
        TransitionFactory(source_episode=source, target_episode=target)

        resolve_episode(progress=progress, gm_notes="Test run.")

        self.assertTrue(
            EpisodeResolution.objects.filter(
                episode=source,
                character_sheet=progress.character_sheet,
            ).exists()
        )

    def test_resolution_captures_era_and_resolver(self):
        """EpisodeResolution records the active era and resolved_by GMProfile."""
        era = EraFactory(status=EraStatus.ACTIVE)
        gm_profile = GMProfileFactory()
        source, target = self._make_story_structure()
        progress = self._make_progress(source)
        TransitionFactory(source_episode=source, target_episode=target)

        resolution = resolve_episode(
            progress=progress,
            resolved_by=gm_profile,
            gm_notes="GM override.",
        )

        self.assertEqual(resolution.era, era)
        self.assertEqual(resolution.resolved_by, gm_profile)
        self.assertEqual(resolution.gm_notes, "GM override.")

    # ------------------------------------------------------------------
    # Several eligible: lowest (order, pk) fires (#3565)
    # ------------------------------------------------------------------

    def test_lowest_order_transition_fires_when_multiple_eligible(self):
        """Two eligible transitions: the lowest-order one fires automatically."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)
        first = TransitionFactory(source_episode=source, target_episode=target, order=0)
        other_target = EpisodeFactory(chapter=source.chapter)
        TransitionFactory(source_episode=source, target_episode=other_target, order=1)

        resolution = resolve_episode(progress=progress)

        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, target)
        self.assertEqual(resolution.chosen_transition, first)

    def test_lowest_pk_tiebreaks_when_order_equal(self):
        """Two eligible transitions with equal order: the lower-pk one fires."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)
        first = TransitionFactory(source_episode=source, target_episode=target, order=0)
        other_target = EpisodeFactory(chapter=source.chapter)
        second = TransitionFactory(source_episode=source, target_episode=other_target, order=0)
        self.assertLess(first.pk, second.pk)

        resolution = resolve_episode(progress=progress)

        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, target)
        self.assertEqual(resolution.chosen_transition, first)

    # ------------------------------------------------------------------
    # No eligible transitions
    # ------------------------------------------------------------------

    def test_no_eligible_transition_raises_when_no_transitions_defined(self):
        """Episode with no outbound transitions raises NoEligibleTransitionError."""
        source, _unused = self._make_story_structure()
        progress = self._make_progress(source)

        with self.assertRaises(NoEligibleTransitionError):
            resolve_episode(progress=progress)

    def test_no_eligible_transition_raises_when_progression_unmet(self):
        """Episode whose gating beat is unmet propagates ProgressionRequirementNotMetError."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)

        # Gating beat that hasn't been satisfied.
        beat = BeatFactory(episode=source, outcome=BeatOutcome.UNSATISFIED)
        EpisodeProgressionRequirementFactory(
            episode=source, beat=beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionFactory(source_episode=source, target_episode=target)

        with self.assertRaises(ProgressionRequirementNotMetError):
            resolve_episode(progress=progress)

    # ------------------------------------------------------------------
    # Branching: routing requirements filter which transitions are eligible
    # ------------------------------------------------------------------

    def test_branching_transition_selected_by_routing_outcome(self):
        """Only the transition whose routing beat matches fires."""
        source, target_success = self._make_story_structure()
        target_failure = EpisodeFactory(chapter=source.chapter)
        progress = self._make_progress(source)

        mission_beat = BeatFactory(episode=source, outcome=BeatOutcome.SUCCESS)

        success_t = TransitionFactory(source_episode=source, target_episode=target_success, order=0)
        TransitionRequiredOutcomeFactory(
            transition=success_t, beat=mission_beat, required_outcome=BeatOutcome.SUCCESS
        )

        _failure_t = TransitionFactory(
            source_episode=source, target_episode=target_failure, order=1
        )
        TransitionRequiredOutcomeFactory(
            transition=_failure_t, beat=mission_beat, required_outcome=BeatOutcome.FAILURE
        )

        resolution = resolve_episode(progress=progress)

        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, target_success)
        self.assertEqual(resolution.chosen_transition, success_t)


class ResolveEpisodeStoryCascadeTests(EvenniaTestCase):
    """resolve_episode cascades to STORY_AT_MILESTONE beats referencing the advanced story."""

    def test_cascade_flips_gated_story_beat_on_advance(self) -> None:
        from world.stories.constants import (
            BeatPredicateType,
            StoryMilestoneType,
            StoryScope,
        )

        # The referenced story (ref_story) starts at ch1, will advance to ch2.
        ref_sheet = CharacterSheetFactory()
        ref_story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=ref_sheet)
        ref_ch1 = ChapterFactory(story=ref_story, order=1)
        ref_ch2 = ChapterFactory(story=ref_story, order=2)
        ref_ep1 = EpisodeFactory(chapter=ref_ch1)
        ref_ep2 = EpisodeFactory(chapter=ref_ch2)
        TransitionFactory(
            source_episode=ref_ep1,
            target_episode=ref_ep2,
        )
        ref_progress = StoryProgressFactory(
            story=ref_story,
            character_sheet=ref_sheet,
            current_episode=ref_ep1,
        )

        # The gated story has a STORY_AT_MILESTONE beat on ref_ch2.
        gated_sheet = CharacterSheetFactory()
        gated_story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=gated_sheet,
        )
        gated_episode = EpisodeFactory(chapter=ChapterFactory(story=gated_story))
        StoryProgressFactory(
            story=gated_story,
            character_sheet=gated_sheet,
            current_episode=gated_episode,
        )
        beat = BeatFactory(
            episode=gated_episode,
            predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
            referenced_story=ref_story,
            referenced_milestone_type=StoryMilestoneType.CHAPTER_REACHED,
            referenced_chapter=ref_ch2,
            outcome=BeatOutcome.UNSATISFIED,
        )

        resolve_episode(progress=ref_progress)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
