from django.test import TestCase

from world.stories.factories import EpisodeFactory


class EpisodeTests(TestCase):
    def test_episode_belongs_to_chapter(self) -> None:
        episode = EpisodeFactory()
        self.assertIsNotNone(episode.chapter)

    def test_episode_has_no_connection_fields(self) -> None:
        # Phase 1: these fields moved to Transition.
        episode = EpisodeFactory()
        self.assertFalse(hasattr(episode, "connection_to_next"))
        self.assertFalse(hasattr(episode, "connection_summary"))
