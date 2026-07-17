"""Natural key tests for PathGiftGrant + TraditionGiftGrant (#2474 Task 1).

Both models already have unique constraints on (path, gift) / (tradition, gift) --
these tests prove the NaturalKeyMixin wiring round-trips through
``get_by_natural_key`` and that Django's natural-key serialization emits no raw
FK pks, which is what Task 2's export/import pipeline relies on.
"""

from django.core import serializers
from django.test import TestCase

from world.magic.factories import PathGiftGrantFactory, TraditionGiftGrantFactory
from world.magic.models.grants import PathGiftGrant, TraditionGiftGrant


class PathGiftGrantNaturalKeyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grant = PathGiftGrantFactory()

    def test_round_trip(self):
        nk = self.grant.natural_key()
        self.assertEqual(PathGiftGrant.objects.get_by_natural_key(*nk).pk, self.grant.pk)

    def test_serializes_with_natural_keys(self):
        data = serializers.serialize(
            "json", [self.grant], use_natural_foreign_keys=True, use_natural_primary_keys=True
        )
        self.assertNotIn(f'"path": {self.grant.path_id}', data)
        self.assertNotIn(f'"gift": {self.grant.gift_id}', data)


class TraditionGiftGrantNaturalKeyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grant = TraditionGiftGrantFactory()

    def test_round_trip(self):
        nk = self.grant.natural_key()
        self.assertEqual(TraditionGiftGrant.objects.get_by_natural_key(*nk).pk, self.grant.pk)

    def test_serializes_with_natural_keys(self):
        data = serializers.serialize(
            "json", [self.grant], use_natural_foreign_keys=True, use_natural_primary_keys=True
        )
        self.assertNotIn(f'"tradition": {self.grant.tradition_id}', data)
        self.assertNotIn(f'"gift": {self.grant.gift_id}', data)
