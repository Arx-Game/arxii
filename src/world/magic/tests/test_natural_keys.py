"""Natural key tests for the magic catalog (#2474 Task 1 + #2486).

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


class TechniqueNaturalKeyRoundTripTest(TestCase):
    """#2486: Technique's own (gift, name) natural key round-trips."""

    def test_natural_key_round_trip(self) -> None:
        technique = TechniqueFactory(name="Ember Lash", damage_profile=False)
        key = technique.natural_key()
        assert key[-1] == "Ember Lash"
        assert Technique.objects.get_by_natural_key(*key) == technique


class PayloadNaturalKeyTest(TestCase):
    """#2486: payload child rows carry composite natural keys."""

    def test_damage_profile_untyped_round_trip(self) -> None:
        """Null damage_type exercises the mixin's None-expansion path."""
        from world.magic.factories import TechniqueDamageProfileFactory
        from world.magic.models import TechniqueDamageProfile

        profile = TechniqueDamageProfileFactory(damage_type=None)
        assert TechniqueDamageProfile.objects.get_by_natural_key(*profile.natural_key()) == profile

    def test_capability_grant_round_trip(self) -> None:
        from world.magic.factories import TechniqueCapabilityGrantFactory
        from world.magic.models import TechniqueCapabilityGrant

        grant = TechniqueCapabilityGrantFactory()
        assert TechniqueCapabilityGrant.objects.get_by_natural_key(*grant.natural_key()) == grant


class VocabNaturalKeyTest(TestCase):
    """#2486: name-keyed vocabulary models for FK-target portability."""

    def test_portal_anchor_kind_round_trip(self) -> None:
        from world.magic.models import PortalAnchorKind

        kind = PortalAnchorKind.objects.create(name="Mirror")
        assert PortalAnchorKind.objects.get_by_natural_key(*kind.natural_key()) == kind

    def test_achievement_round_trip(self) -> None:
        from world.achievements.models import Achievement

        ach = Achievement.objects.create(name="First Steps", slug="first-steps", description="x")
        assert Achievement.objects.get_by_natural_key(*ach.natural_key()) == ach
