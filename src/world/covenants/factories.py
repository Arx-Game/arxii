"""FactoryBoy factories for covenant models."""

import factory
from factory import django as factory_django

from world.covenants.constants import CovenantType, RoleArchetype
from world.covenants.models import CharacterCovenantRole, CovenantRole, GearArchetypeCompatibility
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


class CharacterCovenantRoleFactory(factory_django.DjangoModelFactory):
    """Factory for CharacterCovenantRole.

    No django_get_or_create — the model's unique constraint is partial
    (only enforced when left_at IS NULL), so get_or_create on
    (character_sheet, covenant_role) would silently return an existing
    *ended* assignment when a test wants a fresh active one. Tests that
    need lookup-or-create semantics should query directly.
    """

    class Meta:
        model = CharacterCovenantRole

    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    covenant_role = factory.SubFactory(CovenantRoleFactory)
