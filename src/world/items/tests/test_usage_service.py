from django.test import TestCase


class ConsumeItemChargesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.items.factories import ItemTemplateFactory

        cls.template = ItemTemplateFactory(is_consumable=True, max_charges=2)

    def _consumable(self, *, charges=2, **kw):
        from evennia_extensions.factories import ObjectDBFactory
        from world.items.factories import ItemInstanceFactory

        return ItemInstanceFactory(
            template=self.template,
            charges=charges,
            quality_tier=None,
            game_object=ObjectDBFactory(),
            **kw,
        )

    def test_decrement_writes_activated_event(self):
        from world.items.constants import OwnershipEventType
        from world.items.services.usage import consume_item_charges

        inst = self._consumable(charges=2)
        consume_item_charges(item_instance=inst, amount=1)
        inst.refresh_from_db()
        self.assertEqual(inst.charges, 1)
        self.assertTrue(
            inst.ownership_events.filter(event_type=OwnershipEventType.ACTIVATED).exists()
        )

    def test_no_charges_raises(self):
        from world.items.exceptions import NoChargesRemaining
        from world.items.services.usage import consume_item_charges

        with self.assertRaises(NoChargesRemaining):
            consume_item_charges(item_instance=self._consumable(charges=0))

    def test_hard_delete_bare_instance_at_zero(self):
        from world.items.constants import OwnershipEventType
        from world.items.models import ItemInstance, OwnershipEvent
        from world.items.services.usage import consume_item_charges

        inst = self._consumable(charges=1)  # bare: no custom name/tier/facets
        self.assertFalse(inst.differs_from_template)
        pk = inst.pk
        consume_item_charges(item_instance=inst, amount=1)
        self.assertFalse(ItemInstance.objects.filter(pk=pk).exists())
        self.assertTrue(
            OwnershipEvent.objects.filter(event_type=OwnershipEventType.CONSUMED).exists()
        )

    def test_soft_delete_special_instance_at_zero(self):
        from world.items.models import ItemInstance
        from world.items.services.usage import consume_item_charges

        inst = self._consumable(charges=1, custom_name="Heirloom Phial")
        pk = inst.pk
        consume_item_charges(item_instance=inst, amount=1)
        row = ItemInstance.objects.get(pk=pk)  # still exists (soft-deleted)
        self.assertIsNotNone(row.destroyed_at)
        self.assertNotIn(pk, set(ItemInstance.objects.in_play().values_list("pk", flat=True)))
