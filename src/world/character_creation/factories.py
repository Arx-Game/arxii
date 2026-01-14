"""
Factory definitions for character creation system tests.
"""

import factory
import factory.django as factory_django

from world.character_creation.models import Beginnings, StartingArea
from world.realms.models import Realm


class RealmFactory(factory_django.DjangoModelFactory):
    """Factory for creating Realm instances."""

    class Meta:
        model = Realm
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"TestRealm{n}")
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")


class StartingAreaFactory(factory_django.DjangoModelFactory):
    """Factory for creating StartingArea instances."""

    class Meta:
        model = StartingArea
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"TestArea{n}")
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")
    realm = factory.SubFactory(RealmFactory)
    is_active = True
    access_level = StartingArea.AccessLevel.ALL
    minimum_trust = 0


class BeginningsFactory(factory_django.DjangoModelFactory):
    """Factory for creating Beginnings instances."""

    class Meta:
        model = Beginnings

    name = factory.Sequence(lambda n: f"TestBeginnings{n}")
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")
    starting_area = factory.SubFactory(StartingAreaFactory)
    is_active = True
    trust_required = 0
    allows_all_species = False
    family_known = True
    sort_order = 0
    cg_point_cost = 0
    social_rank = 0
