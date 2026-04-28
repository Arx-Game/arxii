"""FactoryBoy factories for covenant models."""

import factory
from factory import django as factory_django

from world.covenants.constants import CovenantType, RoleArchetype
from world.covenants.models import CovenantRole, GearArchetypeCompatibility
from world.items.constants import GearArchetype


class CovenantRoleFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantRole."""

    class Meta:
        model = CovenantRole
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Role {n}")
    slug = factory.Sequence(lambda n: f"role-{n}")
    covenant_type = CovenantType.DURANCE
    archetype = RoleArchetype.SWORD
    speed_rank = 5
    description = ""


class GearArchetypeCompatibilityFactory(factory_django.DjangoModelFactory):
    """Factory for GearArchetypeCompatibility."""

    class Meta:
        model = GearArchetypeCompatibility
        django_get_or_create = ("covenant_role", "gear_archetype")

    covenant_role = factory.SubFactory(CovenantRoleFactory)
    gear_archetype = GearArchetype.HEAVY_ARMOR
