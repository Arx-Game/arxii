"""Tests for the CG gift/technique availability service (#2426)."""

from django.test import TestCase

from world.classes.factories import PathFactory
from world.magic.factories import (
    GiftFactory,
    PathGiftGrantFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.services.cg_catalog import get_gift_options, get_technique_options


class TechniqueOptionsTest(TestCase):
    """get_technique_options resolves pool (path) + signature (tradition) sets."""

    @classmethod
    def setUpTestData(cls):
        cls.path = PathFactory()
        cls.gift = GiftFactory()
        cls.tradition = TraditionFactory()
        cls.other_tradition = TraditionFactory()

        path_grant = PathGiftGrantFactory(path=cls.path, gift=cls.gift)
        cls.pool_techniques = TechniqueFactory.create_batch(2, gift=cls.gift)
        path_grant.starter_techniques.set(cls.pool_techniques)

        tradition_grant = TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        cls.signature_technique = TechniqueFactory(gift=cls.gift)
        tradition_grant.signature_techniques.set([cls.signature_technique])

        # A second tradition has an authored grant row but no signature techniques.
        TraditionGiftGrantFactory(tradition=cls.other_tradition, gift=cls.gift)

    def test_pool_and_signature_for_tradition_with_signature(self):
        options = get_technique_options(self.path, self.gift, self.tradition)

        self.assertCountEqual(options.pool, self.pool_techniques)
        self.assertEqual(options.signature, [self.signature_technique])

    def test_pool_present_signature_empty_for_other_tradition(self):
        options = get_technique_options(self.path, self.gift, self.other_tradition)

        self.assertCountEqual(options.pool, self.pool_techniques)
        self.assertEqual(options.signature, [])

    def test_no_grant_rows_returns_empty_options(self):
        unlinked_path = PathFactory()
        unlinked_tradition = TraditionFactory()

        options = get_technique_options(unlinked_path, self.gift, unlinked_tradition)

        self.assertEqual(options.pool, [])
        self.assertEqual(options.signature, [])


class GiftOptionsTest(TestCase):
    """get_gift_options excludes gifts with zero combined pool U signature availability."""

    @classmethod
    def setUpTestData(cls):
        cls.path = PathFactory()
        cls.tradition = TraditionFactory()

        cls.available_gift = GiftFactory()
        path_grant = PathGiftGrantFactory(path=cls.path, gift=cls.available_gift)
        path_grant.starter_techniques.set(TechniqueFactory.create_batch(2, gift=cls.available_gift))
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.available_gift)

        # Authored tradition grant, but neither pool nor signature techniques attached.
        cls.empty_gift = GiftFactory()
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.empty_gift)

    def test_excludes_gift_with_no_available_techniques(self):
        gifts = get_gift_options(self.tradition, self.path)

        self.assertIn(self.available_gift, gifts)
        self.assertNotIn(self.empty_gift, gifts)
