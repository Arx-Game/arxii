"""Tests for the PathGiftGrant model (#1579, ADR-0055).

PathGiftGrant authors the (Path x Gift) -> curated starter technique set that a
character receives when they cross into a path.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.classes.factories import PathFactory
from world.magic.factories import GiftFactory, TechniqueFactory
from world.magic.models import PathGiftGrant


class PathGiftGrantModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.path = PathFactory(name="Steel Warden")
        cls.gift = GiftFactory(name="Pyromancy")
        cls.other_gift = GiftFactory(name="Cryomancy")
        cls.gift_technique = TechniqueFactory(name="Flame Lash", gift=cls.gift)
        cls.foreign_technique = TechniqueFactory(name="Ice Shard", gift=cls.other_gift)

    def test_str(self):
        grant = PathGiftGrant.objects.create(path=self.path, gift=self.gift)
        self.assertEqual(str(grant), f"{self.path} grants {self.gift}")

    def test_unique_per_path_and_gift(self):
        PathGiftGrant.objects.create(path=self.path, gift=self.gift)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PathGiftGrant.objects.create(path=self.path, gift=self.gift)

    def test_clean_accepts_techniques_of_the_grants_gift(self):
        grant = PathGiftGrant.objects.create(path=self.path, gift=self.gift)
        grant.starter_techniques.add(self.gift_technique)
        grant.full_clean()  # should not raise

    def test_clean_rejects_technique_of_another_gift(self):
        grant = PathGiftGrant.objects.create(path=self.path, gift=self.gift)
        grant.starter_techniques.add(self.foreign_technique)
        with self.assertRaises(ValidationError):
            grant.full_clean()
