"""Tests for world.stories.services.episodes."""

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory
from world.stories.constants import BeatOutcome, EraStatus, TransitionMode
from world.stories.exceptions import AmbiguousTransitionError, NoEligibleTransitionError
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

    def test_auto_transition_fires_and_advances_progress(self):
        """Single AUTO eligible transition advances progress to target."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)
        transition = TransitionFactory(
            source_episode=source,
            target_episode=target,
            mode=TransitionMode.AUTO,
        )

        resolution = resolve_episode(progress=progress)

        self.assertIsInstance(resolution, EpisodeResolution)
        self.assertEqual(resolution.chosen_transition, transition)
        self.assertEqual(resolution.episode, source)

        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, target)

    def test_explicit_chosen_transition_fires_correctly(self):
        """Passing chosen_transition explicitly advances to the right target."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)
        t1 = TransitionFactory(
            source_episode=source,
            target_episode=target,
            mode=TransitionMode.GM_CHOICE,
            order=0,
        )
        other_target = EpisodeFactory(chapter=source.chapter)
        TransitionFactory(
            source_episode=source,
            target_episode=other_target,
            mode=TransitionMode.GM_CHOICE,
            order=1,
        )

        resolution = resolve_episode(progress=progress, chosen_transition=t1)

        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, target)
        self.assertEqual(resolution.chosen_transition, t1)

    def test_null_target_parks_progress_at_frontier(self):
        """Transition with target_episode=None advances to None (frontier)."""
        source, _unused = self._make_story_structure()
        progress = self._make_progress(source)
        frontier_transition = TransitionFactory(
            source_episode=source,
            target_episode=None,
            mode=TransitionMode.AUTO,
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
    # Ambiguous / GM_CHOICE paths
    # ------------------------------------------------------------------

    def test_gm_choice_required_when_multiple_eligible(self):
        """Two eligible transitions with no chosen_transition → AmbiguousTransitionError."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)
        TransitionFactory(source_episode=source, target_episode=target, order=0)
        other_target = EpisodeFactory(chapter=source.chapter)
        TransitionFactory(source_episode=source, target_episode=other_target, order=1)

        with self.assertRaises(AmbiguousTransitionError):
            resolve_episode(progress=progress)

    def test_gm_choice_with_explicit_chosen_advances_correctly(self):
        """With multiple eligible, explicit chosen_transition resolves normally."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)
        t1 = TransitionFactory(source_episode=source, target_episode=target, order=0)
        other_target = EpisodeFactory(chapter=source.chapter)
        TransitionFactory(source_episode=source, target_episode=other_target, order=1)

        resolution = resolve_episode(progress=progress, chosen_transition=t1)

        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, target)
        self.assertEqual(resolution.chosen_transition, t1)

    def test_gm_choice_mode_without_chosen_raises_ambiguous(self):
        """Single eligible transition with mode=GM_CHOICE raises AmbiguousTransitionError."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)
        TransitionFactory(
            source_episode=source,
            target_episode=target,
            mode=TransitionMode.GM_CHOICE,
        )

        with self.assertRaises(AmbiguousTransitionError):
            resolve_episode(progress=progress)

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
        """Episode whose gating beat is unmet raises NoEligibleTransitionError."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)

        # Gating beat that hasn't been satisfied.
        beat = BeatFactory(episode=source, outcome=BeatOutcome.UNSATISFIED)
        EpisodeProgressionRequirementFactory(
            episode=source, beat=beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionFactory(source_episode=source, target_episode=target)

        with self.assertRaises(NoEligibleTransitionError):
            resolve_episode(progress=progress)

    def test_chosen_transition_not_in_eligible_set_raises(self):
        """Passing a transition from a different episode raises NoEligibleTransitionError."""
        source, target = self._make_story_structure()
        progress = self._make_progress(source)

        # The episode has one valid AUTO transition.
        TransitionFactory(source_episode=source, target_episode=target)

        # An unrelated transition from a different episode.
        other_episode = EpisodeFactory(chapter=source.chapter)
        unrelated_transition = TransitionFactory(
            source_episode=other_episode,
            target_episode=target,
        )

        with self.assertRaises(NoEligibleTransitionError):
            resolve_episode(progress=progress, chosen_transition=unrelated_transition)

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

    # ------------------------------------------------------------------
    # Mixed AUTO / GM_CHOICE eligibility
    # ------------------------------------------------------------------

    def test_mixed_auto_and_gm_choice_eligible_raises_ambiguous(self):
        """Two eligible transitions — one AUTO, one GM_CHOICE — raise AmbiguousTransitionError
        when no chosen_transition is passed, because multiple eligible always requires explicit
        selection regardless of mode."""
        source, target = self._make_story_structure()
        other_target = EpisodeFactory(chapter=source.chapter)
        progress = self._make_progress(source)

        TransitionFactory(
            source_episode=source,
            target_episode=target,
            mode=TransitionMode.AUTO,
            order=0,
        )
        TransitionFactory(
            source_episode=source,
            target_episode=other_target,
            mode=TransitionMode.GM_CHOICE,
            order=1,
        )

        with self.assertRaises(AmbiguousTransitionError):
            resolve_episode(progress=progress)

    def test_mixed_eligible_set_respects_chosen_auto_transition(self):
        """With a mixed AUTO/GM_CHOICE eligible set, passing the AUTO transition advances
        correctly."""
        source, target = self._make_story_structure()
        other_target = EpisodeFactory(chapter=source.chapter)
        progress = self._make_progress(source)

        auto_t = TransitionFactory(
            source_episode=source,
            target_episode=target,
            mode=TransitionMode.AUTO,
            order=0,
        )
        TransitionFactory(
            source_episode=source,
            target_episode=other_target,
            mode=TransitionMode.GM_CHOICE,
            order=1,
        )

        resolution = resolve_episode(progress=progress, chosen_transition=auto_t)

        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, target)
        self.assertEqual(resolution.chosen_transition, auto_t)

    def test_mixed_eligible_set_respects_chosen_gm_choice_transition(self):
        """With a mixed AUTO/GM_CHOICE eligible set, passing the GM_CHOICE transition advances
        correctly."""
        source, target = self._make_story_structure()
        other_target = EpisodeFactory(chapter=source.chapter)
        progress = self._make_progress(source)

        TransitionFactory(
            source_episode=source,
            target_episode=target,
            mode=TransitionMode.AUTO,
            order=0,
        )
        gm_t = TransitionFactory(
            source_episode=source,
            target_episode=other_target,
            mode=TransitionMode.GM_CHOICE,
            order=1,
        )

        resolution = resolve_episode(progress=progress, chosen_transition=gm_t)

        progress.refresh_from_db()
        self.assertEqual(progress.current_episode, other_target)
        self.assertEqual(resolution.chosen_transition, gm_t)
