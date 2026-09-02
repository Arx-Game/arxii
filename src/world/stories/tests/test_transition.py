from django.test import TestCase

from world.stories.factories import EpisodeFactory, TransitionFactory


class TransitionTests(TestCase):
    def test_transition_connects_two_episodes(self):
        source = EpisodeFactory()
        target = EpisodeFactory(chapter=source.chapter)
        transition = TransitionFactory(source_episode=source, target_episode=target)
        self.assertEqual(transition.source_episode, source)
        self.assertEqual(transition.target_episode, target)

    def test_transition_can_have_null_target_for_unauthored_frontier(self):
        transition = TransitionFactory(target_episode=None)
        self.assertIsNone(transition.target_episode)
