"""Admin inline edits to routing rules must drop the transition's rule cache (#3563).

TransitionRequiredOutcomeViewSet.perform_create/update/destroy pop
Transition.cached_required_outcomes from the instance's __dict__ after a
write through the API. The admin's TransitionRequiredOutcomeInline is a
second, independent write path onto the same TransitionRequiredOutcome rows
and needs the same invalidation, or a Transition read earlier in the same
process (e.g. by a GM queue view) would keep serving the stale rule set for
the rest of the process.
"""

from types import SimpleNamespace

from django.contrib import admin
from django.test import RequestFactory, TestCase

from world.stories.admin import TransitionAdmin
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.models import Transition


class TransitionAdminCacheInvalidationTests(TestCase):
    def test_save_related_drops_cached_required_outcomes(self) -> None:
        source_episode = EpisodeFactory()
        transition = TransitionFactory(source_episode=source_episode, target_episode=None)
        beat = BeatFactory(episode=source_episode)
        TransitionRequiredOutcomeFactory(transition=transition, beat=beat)

        # Populate the cache, mirroring how a GM queue read would prime it
        # before the admin edit happens later in the same process.
        _ = transition.cached_required_outcomes
        self.assertIn("cached_required_outcomes", transition.__dict__)

        request = RequestFactory().post("/admin/stories/transition/1/change/")
        form = SimpleNamespace(instance=transition, save_m2m=lambda: None)
        TransitionAdmin(Transition, admin.site).save_related(request, form, [], True)

        self.assertNotIn("cached_required_outcomes", transition.__dict__)
