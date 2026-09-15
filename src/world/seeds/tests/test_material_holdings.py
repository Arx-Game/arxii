"""The houses demo seeds a quarry and a lumber camp with material sources (#696 gap 8)."""

from django.test import TestCase, override_settings

from world.items.models import MaterialCategory
from world.seeds.houses import seed_houses_demo
from world.societies.houses.models import DomainHolding, HoldingKind, HoldingMaterialSource


@override_settings(SEED_SAMPLE_CONTENT=True)
class MaterialHoldingSeedTests(TestCase):
    def test_kinds_holdings_and_sources_seed_idempotently(self) -> None:
        seed_houses_demo()
        seed_houses_demo()

        for name in ("Quarry PLACEHOLDER", "Lumber camp PLACEHOLDER"):
            kind = HoldingKind.objects.get(name=name)
            self.assertEqual(DomainHolding.objects.filter(kind=kind).count(), 1)
            holding = DomainHolding.objects.get(kind=kind)
            self.assertEqual(HoldingMaterialSource.objects.filter(holding=holding).count(), 1)
        self.assertTrue(MaterialCategory.objects.filter(name="Stone PLACEHOLDER").exists())
