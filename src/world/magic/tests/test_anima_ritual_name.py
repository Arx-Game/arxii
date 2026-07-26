"""Player anima ritual names must not collide (#2724)."""

from django.test import TestCase

from world.magic.constants import RitualExecutionKind
from world.magic.models.rituals import Ritual
from world.magic.services.anima import _uniquify_ritual_name


class UniquifyRitualNameTests(TestCase):
    """``Ritual.name`` is unique=True and player names derive from first names."""

    def test_free_name_is_returned_unchanged(self) -> None:
        self.assertEqual(_uniquify_ritual_name("Dawn Offering"), "Dawn Offering")

    def test_taken_name_gets_a_numeric_suffix(self) -> None:
        Ritual.objects.create(
            name="Dawn Offering",
            description="",
            narrative_prose="",
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
        )
        self.assertEqual(_uniquify_ritual_name("Dawn Offering"), "Dawn Offering (2)")

    def test_suffix_increments_past_multiple_collisions(self) -> None:
        for name in ("Dawn Offering", "Dawn Offering (2)", "Dawn Offering (3)"):
            Ritual.objects.create(
                name=name,
                description="",
                narrative_prose="",
                execution_kind=RitualExecutionKind.SCENE_ACTION,
                service_function_path="",
            )
        self.assertEqual(_uniquify_ritual_name("Dawn Offering"), "Dawn Offering (4)")

    def test_result_always_fits_the_column(self) -> None:
        max_length = Ritual._meta.get_field("name").max_length
        base = "X" * max_length
        Ritual.objects.create(
            name=base,
            description="",
            narrative_prose="",
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
        )
        result = _uniquify_ritual_name(base)
        self.assertLessEqual(len(result), max_length)
        self.assertNotEqual(result, base)
