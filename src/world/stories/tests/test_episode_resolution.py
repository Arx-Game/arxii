from evennia.utils.test_resources import EvenniaTestCase

from world.stories.factories import EpisodeResolutionFactory, TransitionFactory


class EpisodeResolutionModelTests(EvenniaTestCase):
    """Unit tests for the EpisodeResolution audit ledger model."""

    def test_resolution_records_transition_and_episode(self) -> None:
        """EpisodeResolution stores episode and chosen_transition correctly."""
        transition = TransitionFactory()
        resolution = EpisodeResolutionFactory(
            episode=transition.source_episode,
            chosen_transition=transition,
        )
        self.assertEqual(resolution.episode, transition.source_episode)
        self.assertEqual(resolution.chosen_transition, transition)
        self.assertIsNotNone(resolution.character_sheet)
        self.assertIsNotNone(resolution.resolved_at)

    def test_resolution_allows_null_transition(self) -> None:
        """chosen_transition may be None for frontier-pause resolutions."""
        resolution = EpisodeResolutionFactory(chosen_transition=None)
        self.assertIsNone(resolution.chosen_transition)

    def test_resolution_str_with_transition(self) -> None:
        """__str__ includes episode title and target episode title when transition set."""
        transition = TransitionFactory()
        resolution = EpisodeResolutionFactory(
            episode=transition.source_episode,
            chosen_transition=transition,
        )
        result = str(resolution)
        self.assertIn(transition.source_episode.title, result)
        self.assertIn(transition.target_episode.title, result)

    def test_resolution_str_without_transition(self) -> None:
        """__str__ shows '(frontier)' when chosen_transition is None."""
        resolution = EpisodeResolutionFactory(chosen_transition=None)
        self.assertIn("(frontier)", str(resolution))

    def test_resolution_defaults_optional_fields_to_none(self) -> None:
        """resolved_by and era default to None."""
        resolution = EpisodeResolutionFactory()
        self.assertIsNone(resolution.resolved_by)
        self.assertIsNone(resolution.era)
