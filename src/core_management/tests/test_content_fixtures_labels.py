"""Model resolution by name, ignoring a fixture's (possibly stale) app label.

#2906: the label half of ``obj["model"]`` becomes meaningless once every
first-party app collapses into one Django label. These tests pin the
behaviour that makes that collapse safe: a stale/wrong label still resolves,
and a genuinely unknown model name still fails loudly rather than silently
skipping (the failure mode that would make a whole-repo rename look like a
successful, empty load).
"""

from django.test import TestCase

from core_management.content_fixtures import resolve_fixture_model
from world.magic.models import Technique


class ResolveFixtureModelTest(TestCase):
    def test_ignores_a_stale_app_label(self):
        self.assertIs(resolve_fixture_model("totally_bogus_label.technique"), Technique)

    def test_resolves_the_current_label(self):
        self.assertIs(resolve_fixture_model("magic.technique"), Technique)

    def test_resolves_a_bare_model_name(self):
        self.assertIs(resolve_fixture_model("technique"), Technique)

    def test_unknown_model_name_still_raises(self):
        with self.assertRaises(LookupError):
            resolve_fixture_model("magic.nosuchmodelanywhere")
