"""The houses demo seeds a quarry and a lumber camp with material sources (#696 gap 8)."""

from django.test import TestCase, override_settings

from world.seeds.crafting_materials import seed_crafting_materials
from world.seeds.houses import seed_houses_demo
from world.societies.houses.models import DomainHolding, HoldingKind, HoldingMaterialSource


@override_settings(SEED_SAMPLE_CONTENT=True)
class MaterialHoldingSeedTests(TestCase):
    def test_kinds_holdings_and_sources_seed_idempotently(self) -> None:
        seed_crafting_materials()  # owns the Stone and Wood categories
        seed_houses_demo()
        seed_houses_demo()

        for name in ("Quarry PLACEHOLDER", "Lumber camp PLACEHOLDER"):
            kind = HoldingKind.objects.get(name=name)
            self.assertEqual(DomainHolding.objects.filter(kind=kind).count(), 1)
            holding = DomainHolding.objects.get(kind=kind)
            self.assertEqual(HoldingMaterialSource.objects.filter(holding=holding).count(), 1)
        names = set(HoldingMaterialSource.objects.values_list("material_category__name", flat=True))
        self.assertEqual(names, {"Stone", "Wood"})

    def test_sources_are_skipped_when_the_crafting_seed_has_not_run(self) -> None:
        seed_houses_demo()

        self.assertTrue(HoldingKind.objects.filter(name="Quarry PLACEHOLDER").exists())
        self.assertFalse(HoldingMaterialSource.objects.exists())
