from django.test import TestCase

from world.stories.constants import StoryMaturity
from world.stories.exceptions import MaturityPromotionError
from world.stories.factories import EpisodeFactory, TransitionFactory
from world.stories.services.maturity import promote_episode_maturity


class EpisodeMaturityPromotionTests(TestCase):
    def test_plot_requires_resting_conclusion(self):
        ep = EpisodeFactory(resting_conclusion="", is_ending=True)
        with self.assertRaises(MaturityPromotionError):
            promote_episode_maturity(ep, StoryMaturity.PLOT)

    def test_plot_requires_transition_or_ending(self):
        ep = EpisodeFactory(resting_conclusion="It ends.", is_ending=False)
        with self.assertRaises(MaturityPromotionError):
            promote_episode_maturity(ep, StoryMaturity.PLOT)

    def test_plot_ok_with_conclusion_and_ending(self):
        ep = EpisodeFactory(resting_conclusion="It ends.", is_ending=True)
        promote_episode_maturity(ep, StoryMaturity.PLOT)
        ep.refresh_from_db()
        self.assertEqual(ep.maturity, StoryMaturity.PLOT)

    def test_plot_ok_with_conclusion_and_outbound_transition(self):
        ep = EpisodeFactory(resting_conclusion="More to come.")
        TransitionFactory(source_episode=ep)
        promote_episode_maturity(ep, StoryMaturity.PLOT)
        ep.refresh_from_db()
        self.assertEqual(ep.maturity, StoryMaturity.PLOT)

    def test_demotion_is_unvalidated(self):
        ep = EpisodeFactory(maturity=StoryMaturity.PLOT, resting_conclusion="")
        promote_episode_maturity(ep, StoryMaturity.OUTLINE)
        ep.refresh_from_db()
        self.assertEqual(ep.maturity, StoryMaturity.OUTLINE)
