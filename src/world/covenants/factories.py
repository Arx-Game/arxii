"""FactoryBoy factories for covenant models."""

import factory
from factory import django as factory_django

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType, RoleArchetype
from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantLevelThreshold,
    CovenantRole,
    GearArchetypeCompatibility,
)
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


class SubroleCovenantRoleFactory(CovenantRoleFactory):
    """Factory for sub-role CovenantRole instances.

    Generates a valid sub-role: parent_role and resonance are both set,
    and covenant_type/archetype are inherited from the parent.
    """

    parent_role = factory.SubFactory(CovenantRoleFactory)
    resonance = factory.SubFactory("world.magic.factories.ResonanceFactory")
    unlock_thread_level = 3

    @factory.lazy_attribute
    def covenant_type(self) -> str:
        return self.parent_role.covenant_type

    @factory.lazy_attribute
    def archetype(self) -> str:
        return self.parent_role.archetype


class GearArchetypeCompatibilityFactory(factory_django.DjangoModelFactory):
    """Factory for GearArchetypeCompatibility."""

    class Meta:
        model = GearArchetypeCompatibility
        django_get_or_create = ("covenant_role", "gear_archetype")

    covenant_role = factory.SubFactory(CovenantRoleFactory)
    gear_archetype = GearArchetype.HEAVY_ARMOR


class CovenantFactory(factory_django.DjangoModelFactory):
    """Factory for Covenant."""

    class Meta:
        model = Covenant

    name = factory.Sequence(lambda n: f"Covenant {n}")
    covenant_type = CovenantType.DURANCE
    level = 1
    sworn_objective = "Sworn to test things."


class CharacterCovenantRoleFactory(factory_django.DjangoModelFactory):
    """Factory for CharacterCovenantRole.

    Note: covenant.covenant_type and covenant_role.covenant_type both
    default to DURANCE. If a test wants BATTLE, both kwargs must be
    set explicitly.

    No django_get_or_create — the model's unique constraint is partial
    (only enforced when left_at IS NULL), so get_or_create on
    (character_sheet, covenant) would silently return an existing
    *ended* assignment when a test wants a fresh active one. Tests that
    need lookup-or-create semantics should query directly.
    """

    class Meta:
        model = CharacterCovenantRole

    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    covenant = factory.SubFactory(CovenantFactory)
    covenant_role = factory.SubFactory(CovenantRoleFactory)
    engaged = False


class CovenantLevelThresholdFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantLevelThreshold."""

    class Meta:
        model = CovenantLevelThreshold
        django_get_or_create = ("level",)

    level = factory.Sequence(lambda n: n + 1)
    required_legend = factory.LazyAttribute(lambda o: (o.level - 1) * 100)


def make_engaged_member(
    *,
    character_sheet: object = None,
    covenant: object = None,
    covenant_role: object = None,
) -> CharacterCovenantRole:
    """Create a covenant + active CCR row + set engaged=True, atomically.

    Convenience for tests that exercise role-bonus or pull-eligibility paths.
    Uses the `set_engaged_membership` service so the invariant is enforced
    naturally.
    """
    from world.covenants.services import set_engaged_membership

    sheet = character_sheet or CharacterSheetFactory()
    cov = covenant or CovenantFactory()
    role = covenant_role or CovenantRoleFactory(covenant_type=cov.covenant_type)
    membership = CharacterCovenantRoleFactory(
        character_sheet=sheet,
        covenant=cov,
        covenant_role=role,
    )
    set_engaged_membership(membership=membership)
    return membership
