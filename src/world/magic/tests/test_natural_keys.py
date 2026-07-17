"""Natural key tests for PathGiftGrant + TraditionGiftGrant (#2474 Task 1).

Both models already have unique constraints on (path, gift) / (tradition, gift) --
these tests prove the NaturalKeyMixin wiring round-trips through
``get_by_natural_key`` and that Django's natural-key serialization emits no raw
FK pks, which is what Task 2's export/import pipeline relies on.
"""

from django.core import serializers
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.magic.factories import (
    GiftFactory,
    PathGiftGrantFactory,
    TechniqueFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models.grants import PathGiftGrant, TraditionGiftGrant
from world.magic.models.techniques import Technique


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


class TechniqueNaturalKeyUniquenessTest(TestCase):
    """#2474 review fix: (gift, name) is the declared natural key but had no
    matching DB constraint -- every sibling composite-NK model in this app
    (``PathGiftGrant``, ``TraditionGiftGrant`` above) pairs a NaturalKeyConfig
    with a real UniqueConstraint. Without one, two techniques could share a
    (gift, name) pair and ``get_by_natural_key`` would silently resolve
    whichever row a non-deterministic ``.get()`` returns (or raise
    MultipleObjectsReturned) -- an authored-content-repo round trip authored
    to be identity-stable would not actually be.
    """

    def test_duplicate_gift_and_name_raises_integrity_error(self) -> None:
        gift = GiftFactory()
        TechniqueFactory(gift=gift, name="Duplicate Technique", damage_profile=False)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TechniqueFactory(gift=gift, name="Duplicate Technique", damage_profile=False)

    def test_same_name_different_gift_is_allowed(self) -> None:
        first_gift = GiftFactory()
        second_gift = GiftFactory()
        TechniqueFactory(gift=first_gift, name="Shared Name", damage_profile=False)
        # Must not raise -- name alone is explicitly not unique.
        TechniqueFactory(gift=second_gift, name="Shared Name", damage_profile=False)
        assert Technique.objects.filter(name="Shared Name").count() == 2
