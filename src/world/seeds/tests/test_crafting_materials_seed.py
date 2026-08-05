"""Seed test for the generic material ladders (#2878 Phase F)."""

import datetime

from django.test import TestCase

from world.contributors.factories import ContentContributorFactory
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

    def test_credited_item_template_survives_a_re_press(self) -> None:
        seed_crafting_materials()
        silk = ItemTemplate.objects.get(name="Silk")
        contributor = ContentContributorFactory()
        silk.written_by = contributor
        silk.written_on = datetime.date(2026, 1, 1)
        silk.description = "A human wrote this description of silk."
        silk.value = 999999
        silk.save()

        seed_crafting_materials()

        silk.refresh_from_db()
        self.assertEqual(silk.written_by_id, contributor.pk)
        self.assertEqual(silk.description, "A human wrote this description of silk.")
        self.assertEqual(silk.value, 999999)

    def test_uncredited_item_template_still_refreshes(self) -> None:
        seed_crafting_materials()
        silk = ItemTemplate.objects.get(name="Silk")
        silk.description = "Some stale placeholder text."
        silk.value = 1
        silk.save()

        seed_crafting_materials()

        silk.refresh_from_db()
        self.assertIsNone(silk.written_by_id)
        self.assertEqual(silk.description, "PLACEHOLDER: silk - crafting material.")
        self.assertEqual(silk.value, 625)
