from datetime import timedelta

from django.test import TestCase
from django.utils import timezone


class PurgeExpiredSoftDeletedItemsTests(TestCase):
    """purge_expired_soft_deleted_items() — #1025."""

    @classmethod
    def setUpTestData(cls):
        from evennia_extensions.factories import ObjectDBFactory
        from world.items.factories import ItemInstanceFactory

        cls.ItemInstanceFactory = ItemInstanceFactory
        cls.ObjectDBFactory = ObjectDBFactory

    def _soft_deleted(self, *, age_days: int, **kw):
        when = timezone.now() - timedelta(days=age_days)
        return self.ItemInstanceFactory(
            quality_tier=None,
            game_object=self.ObjectDBFactory(),
            destroyed_at=when,
            **kw,
        )

    def test_non_lore_critical_past_grace_is_purged(self):
        from world.items.models import ItemInstance, OwnershipEvent
        from world.items.services.cleanup import purge_expired_soft_deleted_items

        inst = self._soft_deleted(age_days=40, custom_name="Plain Phial")
        OwnershipEvent.objects.create(item_instance=inst, event_type="consumed")
        pk = inst.pk

        purged = purge_expired_soft_deleted_items(grace=timedelta(days=30))

        self.assertEqual(purged, 1)
        self.assertFalse(ItemInstance.objects.filter(pk=pk).exists())
        self.assertFalse(OwnershipEvent.objects.exists())  # no orphan rows

    def test_within_grace_is_retained(self):
        from world.items.models import ItemInstance
        from world.items.services.cleanup import purge_expired_soft_deleted_items

        inst = self._soft_deleted(age_days=5, custom_name="Recent Phial")
        purged = purge_expired_soft_deleted_items(grace=timedelta(days=30))
        self.assertEqual(purged, 0)
        self.assertTrue(ItemInstance.objects.filter(pk=inst.pk).exists())

    def test_lore_value_survives_forever(self):
        from world.items.models import ItemInstance
        from world.items.services.cleanup import purge_expired_soft_deleted_items

        inst = self._soft_deleted(age_days=400, lore_value=3)
        purge_expired_soft_deleted_items(grace=timedelta(days=30))
        self.assertTrue(ItemInstance.objects.filter(pk=inst.pk).exists())

    def test_facet_survives_forever(self):
        from world.items.factories import ItemFacetFactory
        from world.items.models import ItemInstance
        from world.items.services.cleanup import purge_expired_soft_deleted_items

        inst = self._soft_deleted(age_days=400)
        ItemFacetFactory(item_instance=inst)
        purge_expired_soft_deleted_items(grace=timedelta(days=30))
        self.assertTrue(ItemInstance.objects.filter(pk=inst.pk).exists())

    def test_transfer_provenance_survives_forever(self):
        from world.items.models import ItemInstance, OwnershipEvent
        from world.items.services.cleanup import purge_expired_soft_deleted_items

        inst = self._soft_deleted(age_days=400)
        OwnershipEvent.objects.create(item_instance=inst, event_type="given")
        purge_expired_soft_deleted_items(grace=timedelta(days=30))
        self.assertTrue(ItemInstance.objects.filter(pk=inst.pk).exists())

    def test_in_play_items_never_purged(self):
        from world.items.models import ItemInstance
        from world.items.services.cleanup import purge_expired_soft_deleted_items

        inst = self.ItemInstanceFactory(quality_tier=None)  # destroyed_at=None
        purge_expired_soft_deleted_items(grace=timedelta(days=30))
        self.assertTrue(ItemInstance.objects.filter(pk=inst.pk).exists())

    def test_default_grace_from_settings(self):
        from django.test import override_settings

        from world.items.models import ItemInstance
        from world.items.services.cleanup import purge_expired_soft_deleted_items

        inst = self._soft_deleted(age_days=40, custom_name="Plain")
        with override_settings(ITEM_SOFT_DELETE_GRACE_DAYS=30):
            purge_expired_soft_deleted_items()  # no grace arg → settings
        self.assertFalse(ItemInstance.objects.filter(pk=inst.pk).exists())
