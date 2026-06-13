from django.test import TestCase

from world.items.constants import GearArchetype, OwnershipEventType
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import OwnershipEvent
from world.items.services.durability import decrement_item_durability


class DecrementDurabilityTests(TestCase):
    def _armor(self, durability):
        tmpl = ItemTemplateFactory(armor=True, name=f"arm-{durability}", max_durability=10)
        return ItemInstanceFactory(template=tmpl, durability=durability)

    def test_decrement_reduces_durability(self):
        inst = self._armor(5)
        out = decrement_item_durability(item_instance=inst, amount=2)
        self.assertEqual(out.durability, 3)

    def test_decrement_clamps_at_zero_and_logs_consumed(self):
        inst = self._armor(1)
        decrement_item_durability(item_instance=inst, amount=5)
        inst.refresh_from_db()
        self.assertEqual(inst.durability, 0)
        self.assertTrue(
            OwnershipEvent.objects.filter(
                item_instance=inst, event_type=OwnershipEventType.CONSUMED
            ).exists()
        )

    def test_untracked_item_is_noop(self):
        tmpl = ItemTemplateFactory(name="plain", gear_archetype=GearArchetype.OTHER)
        inst = ItemInstanceFactory(template=tmpl, durability=None)
        out = decrement_item_durability(item_instance=inst)
        self.assertIsNone(out.durability)

    def test_decrement_invalidates_effective_cache(self):
        inst = self._armor(1)
        _ = inst.effective_armor_soak  # prime cache
        decrement_item_durability(item_instance=inst, amount=1)
        self.assertEqual(inst.effective_armor_soak, 0)  # broken -> 0
