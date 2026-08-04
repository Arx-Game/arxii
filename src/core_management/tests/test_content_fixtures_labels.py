"""Model resolution by name, ignoring a fixture's (possibly stale) app label.

#2906: the label half of ``obj["model"]`` becomes meaningless once every
first-party app collapses into one Django label. These tests pin the
behaviour that makes that collapse safe: a stale/wrong label still resolves,
and a genuinely unknown model name still fails loudly rather than silently
skipping (the failure mode that would make a whole-repo rename look like a
successful, empty load).
"""

from django.test import TestCase

from core import app_domains
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


class ResolveFixtureModelCollisionTest(TestCase):
    """Pins the multi-candidate branch of ``resolve_model_by_name`` with a
    fabricated collision, rather than depending on a live one.

    This used to ride a genuine accident: ``AchievementRequirement`` existed
    under both ``world.achievements`` and ``world.progression`` with disjoint
    fields. #2906's Task 3 renamed the ``achievements`` one to
    ``AchievementStatRequirement``, which resolved that collision and would
    have silently degraded these tests to the single-candidate branch (still
    green, but no longer exercising label disambiguation or the "still
    ambiguous" error path at all).

    So the collision is fabricated here instead: two throwaway stand-in
    "model" objects (only ``__name__`` and ``_meta.app_label`` are ever read
    by the resolver) are injected under one shared name directly into the
    resolver's cached ``_model_index()``, for the duration of each test, then
    removed. This keeps testing the real property -- multiple installed
    models sharing a lowercase name, disambiguated by label -- permanently,
    without depending on a transient accident of the current model set.
    """

    SYNTHETIC_NAME = "syntheticcollisionwidget"

    def setUp(self):
        super().setUp()
        index = app_domains._model_index()  # force-build/reuse the real cache
        self._prior_entry = index.get(self.SYNTHETIC_NAME)
        self._widget_a = _FakeModel("SyntheticCollisionWidget", "achievements")
        self._widget_b = _FakeModel("SyntheticCollisionWidget", "progression")
        index[self.SYNTHETIC_NAME] = [self._widget_a, self._widget_b]
        self.addCleanup(self._restore_index, index)

    def _restore_index(self, index):
        if self._prior_entry is None:
            index.pop(self.SYNTHETIC_NAME, None)
        else:
            index[self.SYNTHETIC_NAME] = self._prior_entry

    def test_colliding_name_resolves_via_its_label(self):
        self.assertIs(
            resolve_fixture_model(f"achievements.{self.SYNTHETIC_NAME}"),
            self._widget_a,
        )
        self.assertIs(
            resolve_fixture_model(f"progression.{self.SYNTHETIC_NAME}"),
            self._widget_b,
        )

    def test_colliding_name_without_a_usable_label_raises(self):
        """No label, and a label that matches neither candidate, are both ambiguous."""
        with self.assertRaises(LookupError) as no_label:
            resolve_fixture_model(self.SYNTHETIC_NAME)
        self.assertIn("achievements.SyntheticCollisionWidget", str(no_label.exception))
        self.assertIn("progression.SyntheticCollisionWidget", str(no_label.exception))

        with self.assertRaises(LookupError) as wrong_label:
            resolve_fixture_model(f"totally_bogus_label.{self.SYNTHETIC_NAME}")
        self.assertIn("achievements.SyntheticCollisionWidget", str(wrong_label.exception))
        self.assertIn("progression.SyntheticCollisionWidget", str(wrong_label.exception))


class _FakeModel:
    """Standin for a model class, carrying only what ``resolve_model_by_name`` reads.

    Not a real Django model -- deliberately so. A genuine collision between two
    real models is exactly the accident #2906's Task 3 removed; using plain
    objects here makes the synthetic collision permanent and immune to any
    future rename among real models.
    """

    def __init__(self, name: str, app_label: str) -> None:
        self.__name__ = name
        self._meta = _FakeMeta(app_label)


class _FakeMeta:
    def __init__(self, app_label: str) -> None:
        self.app_label = app_label
