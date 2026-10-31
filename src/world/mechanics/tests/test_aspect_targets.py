"""One modifier target per Aspect (#4827): the service function and the seed."""

from django.test import TestCase, override_settings

from world.classes.factories import AspectFactory
from world.mechanics.constants import ASPECT_CATEGORY_NAME
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import ModifierTarget
from world.mechanics.services import ensure_aspect_target
from world.seeds.levers import ensure_aspect_targets


class EnsureAspectTargetTests(TestCase):
    def test_makes_the_aspect_category_target_once(self):
        warfare = AspectFactory(name="Warfare")
        first = ensure_aspect_target(warfare)
        second = ensure_aspect_target(warfare)
        assert first is not None
        assert first.pk == second.pk
        assert (first.name, first.category.name) == ("warfare", ASPECT_CATEGORY_NAME)
        assert first.target_aspect == warfare
        assert ModifierTarget.objects.filter(target_aspect=warfare).count() == 1

    def test_a_two_word_aspect_is_named_the_pastes_way(self):
        target = ensure_aspect_target(AspectFactory(name="Court Intrigue"))
        assert target is not None
        assert target.name == "court_intrigue"

    def test_an_unlinked_target_of_the_same_name_in_the_aspect_category_is_adopted(self):
        scholarship = AspectFactory(name="Scholarship")
        orphan = ModifierTargetFactory(
            name="scholarship", category=ModifierCategoryFactory(name=ASPECT_CATEGORY_NAME)
        )
        assert ensure_aspect_target(scholarship) == orphan
        orphan.refresh_from_db()
        assert orphan.target_aspect == scholarship

    def test_a_same_named_target_in_another_category_is_left_alone(self):
        """A check-scoped or stat target already called ``warfare`` keeps its row; two
        categories sharing a name would make the paste refuse the name."""
        warfare = AspectFactory(name="Warfare")
        other = ModifierTargetFactory(
            name="warfare", category=ModifierCategoryFactory(name="check")
        )
        assert ensure_aspect_target(warfare) is None
        assert ModifierTarget.objects.filter(name="warfare").count() == 1
        other.refresh_from_db()
        assert other.target_aspect_id is None


class EnsureAspectTargetsSeedTests(TestCase):
    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_with_sample_content_the_seed_makes_one_target_per_aspect_once(self):
        AspectFactory(name="Subterfuge")
        AspectFactory(name="Diplomacy")
        ensure_aspect_targets()
        ensure_aspect_targets()
        names = sorted(
            ModifierTarget.objects.filter(category__name=ASPECT_CATEGORY_NAME).values_list(
                "name", flat=True
            )
        )
        assert names == ["diplomacy", "subterfuge"]

    @override_settings(SEED_SAMPLE_CONTENT=False)
    def test_without_sample_content_the_seed_invents_nothing(self):
        """Targets are content rows (#2698): on production the Aspect admin's save makes
        them, never a seeder."""
        AspectFactory(name="Subterfuge")
        ensure_aspect_targets()
        assert not ModifierTarget.objects.filter(category__name=ASPECT_CATEGORY_NAME).exists()
