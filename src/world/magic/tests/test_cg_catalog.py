"""Tests for the CG gift/technique availability service (#2426)."""

from django.test import TestCase

from world.classes.factories import PathFactory
from world.magic.constants import GiftKind
from world.magic.factories import (
    GiftFactory,
    PathGiftGrantFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.seeds_cast import get_standalone_cast_template
from world.magic.services.cg_catalog import get_gift_options, get_technique_options


class TechniqueOptionsTest(TestCase):
    """get_technique_options splits the Path's list into open and Tradition-kept halves."""

    @classmethod
    def setUpTestData(cls):
        cls.path = PathFactory()
        cls.gift = GiftFactory()
        cls.tradition = TraditionFactory()
        cls.other_tradition = TraditionFactory()

        cast_template = get_standalone_cast_template()
        path_grant = PathGiftGrantFactory(path=cls.path, gift=cls.gift)
        cls.pool_techniques = TechniqueFactory.create_batch(
            2, gift=cls.gift, action_template=cast_template
        )
        cls.unready_technique = TechniqueFactory(gift=cls.gift)
        cls.special_technique = TechniqueFactory(gift=cls.gift, action_template=cast_template)
        path_grant.starter_techniques.set(
            [*cls.pool_techniques, cls.unready_technique, cls.special_technique]
        )

        # Kept for the tradition, but on another Path's list only (#4555).
        cls.elsewhere_technique = TechniqueFactory(gift=cls.gift, action_template=cast_template)
        PathGiftGrantFactory(path=PathFactory(), gift=cls.gift).starter_techniques.set(
            [cls.elsewhere_technique]
        )

        tradition_grant = TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        tradition_grant.special_techniques.set([cls.special_technique, cls.elsewhere_technique])

        # A second tradition has an authored grant row but no signature techniques.
        TraditionGiftGrantFactory(tradition=cls.other_tradition, gift=cls.gift)

    def test_pool_and_signature_for_tradition_with_signature(self):
        options = get_technique_options(self.path, self.gift, self.tradition)

        self.assertCountEqual(options.pool, self.pool_techniques)
        self.assertEqual(options.tradition, [self.special_technique])

    def test_unready_techniques_are_not_offered(self):
        options = get_technique_options(self.path, self.gift, self.tradition)

        offered_ids = {technique.id for technique in [*options.pool, *options.tradition]}
        self.assertNotIn(self.unready_technique.id, offered_ids)

        all_options = get_technique_options(
            self.path, self.gift, self.tradition, include_unready=True
        )
        all_ids = {technique.id for technique in [*all_options.pool, *all_options.tradition]}
        self.assertIn(self.unready_technique.id, all_ids)

    def test_pool_present_signature_empty_for_other_tradition(self):
        options = get_technique_options(self.path, self.gift, self.other_tradition)

        self.assertCountEqual(options.pool, self.pool_techniques)
        self.assertEqual(options.tradition, [])

    def test_a_tradition_technique_is_offered_only_on_its_paths(self):
        options = get_technique_options(self.path, self.gift, self.tradition)

        offered_ids = {technique.id for technique in [*options.pool, *options.tradition]}
        self.assertNotIn(self.elsewhere_technique.id, offered_ids)

    def test_no_tradition_is_offered_only_the_open_techniques(self):
        options = get_technique_options(self.path, self.gift, None)

        self.assertCountEqual(options.pool, self.pool_techniques)
        self.assertEqual(options.tradition, [])

    def test_no_grant_rows_returns_empty_options(self):
        unlinked_path = PathFactory()
        unlinked_tradition = TraditionFactory()

        options = get_technique_options(unlinked_path, self.gift, unlinked_tradition)

        self.assertEqual(options.pool, [])
        self.assertEqual(options.tradition, [])


class GiftOptionsTest(TestCase):
    """get_gift_options offers every Major Gift with a takeable technique for the Tradition."""

    @classmethod
    def setUpTestData(cls):
        cls.path = PathFactory()
        cls.tradition = TraditionFactory()

        cls.available_gift = GiftFactory()
        path_grant = PathGiftGrantFactory(path=cls.path, gift=cls.available_gift)
        path_grant.starter_techniques.set(
            TechniqueFactory.create_batch(
                2, gift=cls.available_gift, action_template=get_standalone_cast_template()
            )
        )
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.available_gift)

        # Authored tradition grant, but neither pool nor signature techniques attached.
        cls.empty_gift = GiftFactory()
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.empty_gift)

        # The Path's only technique for this gift is kept by another tradition (#4555).
        cls.kept_gift = GiftFactory()
        kept = TechniqueFactory(gift=cls.kept_gift, action_template=get_standalone_cast_template())
        PathGiftGrantFactory(path=cls.path, gift=cls.kept_gift).starter_techniques.set([kept])
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.kept_gift)
        cls.keeper = TraditionFactory()
        TraditionGiftGrantFactory(tradition=cls.keeper, gift=cls.kept_gift).special_techniques.set(
            [kept]
        )

    def test_excludes_gift_with_no_available_techniques(self):
        gifts = get_gift_options(self.tradition, self.path)

        self.assertIn(self.available_gift, gifts)
        self.assertNotIn(self.empty_gift, gifts)

    def test_a_major_gift_the_tradition_does_not_favor_is_offered(self):
        """#4659: a grant row marks a favored Gift; it no longer gates the pick."""
        unfavored = GiftFactory()
        PathGiftGrantFactory(path=self.path, gift=unfavored).starter_techniques.set(
            [TechniqueFactory(gift=unfavored, action_template=get_standalone_cast_template())]
        )

        self.assertIn(unfavored, get_gift_options(self.tradition, self.path))

    def test_a_minor_gift_on_the_path_list_is_not_offered(self):
        minor = GiftFactory(kind=GiftKind.MINOR)
        PathGiftGrantFactory(path=self.path, gift=minor).starter_techniques.set(
            [TechniqueFactory(gift=minor, action_template=get_standalone_cast_template())]
        )

        self.assertNotIn(minor, get_gift_options(self.tradition, self.path))

    def test_a_gift_whose_techniques_another_tradition_keeps_is_not_offered(self):
        self.assertNotIn(self.kept_gift, get_gift_options(self.tradition, self.path))
        self.assertIn(self.kept_gift, get_gift_options(self.keeper, self.path))
