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
from world.achievements.models import (
    AchievementRequirement as AchievementsAchievementRequirement,
)
from world.magic.models import Technique
from world.progression.models.unlocks import (
    AchievementRequirement as ProgressionAchievementRequirement,
)


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

    def test_colliding_name_resolves_via_its_label(self):
        """AchievementRequirement is a genuine, live collision (review finding).

        It exists today under both world.achievements and world.progression
        with disjoint fields. The label half of the key must disambiguate it
        rather than the resolver silently picking whichever model
        apps.get_models() happens to enumerate last. After #2906's Task 3
        renames one of the pair, this still passes (via the single-candidate
        branch) — it isn't tied to the collision persisting.
        """
        self.assertIs(
            resolve_fixture_model("achievements.achievementrequirement"),
            AchievementsAchievementRequirement,
        )
        self.assertIs(
            resolve_fixture_model("progression.achievementrequirement"),
            ProgressionAchievementRequirement,
        )

    def test_colliding_name_without_a_usable_label_raises(self):
        """No label, and a label that matches neither candidate, are both ambiguous."""
        with self.assertRaises(LookupError) as no_label:
            resolve_fixture_model("achievementrequirement")
        self.assertIn("achievements.AchievementRequirement", str(no_label.exception))
        self.assertIn("progression.AchievementRequirement", str(no_label.exception))

        with self.assertRaises(LookupError) as wrong_label:
            resolve_fixture_model("totally_bogus_label.achievementrequirement")
        self.assertIn("achievements.AchievementRequirement", str(wrong_label.exception))
        self.assertIn("progression.AchievementRequirement", str(wrong_label.exception))
