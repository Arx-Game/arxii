"""Seed test for the generic material ladders (#2878 Phase F)."""

from django.test import TestCase

from world.items.models import ItemTemplate, MaterialCategory
from world.seeds.crafting_materials import seed_crafting_materials


class CraftingMaterialsSeedTests(TestCase):
    def test_seed_is_idempotent_and_graded(self) -> None:
        seed_crafting_materials()
        seed_crafting_materials()  # idempotent upsert
        self.assertEqual(MaterialCategory.objects.count(), 5)
        self.assertEqual(ItemTemplate.objects.filter(material_category__isnull=False).count(), 21)
        silk = ItemTemplate.objects.get(name="Silk")
        self.assertEqual(silk.material_grade, 15)
        self.assertEqual(silk.value, 625)
        low = ItemTemplate.objects.get(name="Low Quality Cloth")
        self.assertEqual(low.material_grade, 0)

    def test_no_named_canon_or_gem_rows(self) -> None:
        seed_crafting_materials()
        for absent in ("Alaricite", "Steelsilk", "Precious Stone", "Hazeweed"):
            self.assertFalse(ItemTemplate.objects.filter(name__iexact=absent).exists())
