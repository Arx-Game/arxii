"""Natural-key coverage for the magic catalog models (#2486)."""

from django.db import IntegrityError
from django.test import TestCase

from world.magic.factories import GiftFactory, TechniqueFactory


class TechniqueNaturalKeyTest(TestCase):
    def test_natural_key_round_trip(self) -> None:
        technique = TechniqueFactory(name="Ember Lash")
        key = technique.natural_key()
        assert key[-1] == "Ember Lash"
        from world.magic.models import Technique

        assert Technique.objects.get_by_natural_key(*key) == technique

    def test_name_unique_per_gift(self) -> None:
        gift = GiftFactory()
        TechniqueFactory(name="Ember Lash", gift=gift)
        with self.assertRaises(IntegrityError):
            TechniqueFactory(name="Ember Lash", gift=gift)

    def test_same_name_allowed_across_gifts(self) -> None:
        TechniqueFactory(name="Ember Lash")
        TechniqueFactory(name="Ember Lash")  # factory makes a fresh gift each call


class GrantNaturalKeyTest(TestCase):
    def test_tradition_gift_grant_round_trip(self) -> None:
        from world.magic.models import TraditionGiftGrant

        technique = TechniqueFactory()
        from world.magic.factories import TraditionFactory  # check factories.py if absent

        grant = TraditionGiftGrant.objects.create(tradition=TraditionFactory(), gift=technique.gift)
        assert TraditionGiftGrant.objects.get_by_natural_key(*grant.natural_key()) == grant

    def test_path_gift_grant_round_trip(self) -> None:
        from world.classes.factories import PathFactory
        from world.magic.models import PathGiftGrant

        technique = TechniqueFactory()
        grant = PathGiftGrant.objects.create(path=PathFactory(), gift=technique.gift)
        assert PathGiftGrant.objects.get_by_natural_key(*grant.natural_key()) == grant


class PayloadNaturalKeyTest(TestCase):
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
    def test_portal_anchor_kind_round_trip(self) -> None:
        from world.magic.models import PortalAnchorKind

        kind = PortalAnchorKind.objects.create(name="Mirror")
        assert PortalAnchorKind.objects.get_by_natural_key(*kind.natural_key()) == kind

    def test_achievement_round_trip(self) -> None:
        from world.achievements.models import Achievement

        ach = Achievement.objects.create(name="First Steps", slug="first-steps", description="x")
        assert Achievement.objects.get_by_natural_key(*ach.natural_key()) == ach
