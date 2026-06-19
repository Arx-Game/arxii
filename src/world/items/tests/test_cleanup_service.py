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

    def test_in_world_item_not_purged_and_warns(self):
        # Half-undelete: the game_object was moved back into the world but
        # destroyed_at is still set. Never purge an in-world item — warn instead.
        from world.items.models import ItemInstance
        from world.items.services.cleanup import purge_expired_soft_deleted_items

        in_world = self._soft_deleted(age_days=40, custom_name="Re-homed Phial")
        in_world.game_object.db_location = self.ObjectDBFactory()
        in_world.game_object.save()
        plain = self._soft_deleted(age_days=40, custom_name="Plain Phial")

        with self.assertLogs("world.items.services.cleanup", level="WARNING") as logs:
            purged = purge_expired_soft_deleted_items(grace=timedelta(days=30))

        self.assertEqual(purged, 1)  # only the plain, out-of-world item
        self.assertTrue(ItemInstance.objects.filter(pk=in_world.pk).exists())
        self.assertFalse(ItemInstance.objects.filter(pk=plain.pk).exists())
        self.assertTrue(any(str(in_world.pk) in line for line in logs.output))

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

    def test_mantle_referenced_instance_excluded_sibling_purged(self):
        """A Mantle-referenced instance is excluded; a plain sibling is purged."""
        from world.items.factories import MantleFactory
        from world.items.models import ItemInstance
        from world.items.services.cleanup import purge_expired_soft_deleted_items

        protected_inst = self._soft_deleted(age_days=40, custom_name="Mantle Item")
        plain_inst = self._soft_deleted(age_days=40, custom_name="Plain Item")
        # Attach a Mantle to the protected instance so it has a PROTECT FK.
        MantleFactory(item_instance=protected_inst)

        purged = purge_expired_soft_deleted_items(grace=timedelta(days=30))

        self.assertEqual(purged, 1)
        # The plain sibling must be gone.
        self.assertFalse(ItemInstance.objects.filter(pk=plain_inst.pk).exists())
        # The Mantle-referenced instance must survive.
        self.assertTrue(ItemInstance.objects.filter(pk=protected_inst.pk).exists())

    def test_per_item_protected_error_skips_row_not_whole_batch(self):
        """A ProtectedError on one item skips it; the next item is still purged."""
        from unittest.mock import patch

        from django.db.models import ProtectedError

        from world.items.models import ItemInstance
        from world.items.services.cleanup import purge_expired_soft_deleted_items

        inst_a = self._soft_deleted(age_days=40, custom_name="Protected A")
        inst_b = self._soft_deleted(age_days=40, custom_name="Plain B")
        pk_a = inst_a.pk
        pk_b = inst_b.pk

        call_count = {"n": 0}

        def _side_effect(instance):
            call_count["n"] += 1
            if call_count["n"] == 1:
                msg = "test ProtectedError"
                raise ProtectedError(msg, set())

        with patch(
            "world.items.services.cleanup.hard_delete_item_instance",
            side_effect=_side_effect,
        ):
            purged = purge_expired_soft_deleted_items(grace=timedelta(days=30))

        # Only one deletion succeeded (the second call).
        self.assertEqual(purged, 1)
        # Both rows still exist in the DB because the mock never actually deleted.
        # The key invariant is that no exception escaped the function.
        self.assertTrue(ItemInstance.objects.filter(pk=pk_a).exists())
        self.assertTrue(ItemInstance.objects.filter(pk=pk_b).exists())
