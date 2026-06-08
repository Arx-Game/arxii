"""FactoryBoy factories for covenant models."""

import factory
from factory import django as factory_django

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType, RoleArchetype
from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantLevelThreshold,
    CovenantRite,
    CovenantRiteRolePackage,
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


class CovenantRiteFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantRite — the 'Renew the Oath' reference rite.

    Doubles as integration-test setUp AND staff seed data (per factories-as-seed-data
    convention). The backing Ritual is created via RenewTheOathRitualFactory
    (django_get_or_create on name) so repeated calls in the same test DB never
    produce duplicate Ritual rows. The granted_condition uses UNTIL_END_OF_COMBAT
    duration so the buff expires naturally at encounter end.

    Gate defaults mirror the reference spec:
        min_covenant_level=2, min_members_present=2, base_severity=2,
        severity_per_extra_participant=1, max_severity=None.
    """

    class Meta:
        model = CovenantRite

    ritual = factory.SubFactory("world.magic.factories.RenewTheOathRitualFactory")
    granted_condition = factory.SubFactory(
        "world.conditions.factories.OathboundResolveConditionFactory"
    )
    covenant_type = CovenantType.DURANCE
    min_covenant_level = 2
    min_members_present = 2
    base_severity = 2
    severity_per_extra_participant = 1
    max_severity = None
    duration_rounds = None


class CovenantRiteRolePackageFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantRiteRolePackage — a role/level-gated stat package on a rite.

    No django_get_or_create — the unique constraint is (rite, covenant_role,
    min_covenant_level); callers that need the same band should query directly
    rather than relying on silent get-or-create merges.
    """

    class Meta:
        model = CovenantRiteRolePackage

    rite = factory.SubFactory(CovenantRiteFactory)
    covenant_role = factory.SubFactory(CovenantRoleFactory)
    min_covenant_level = 1
    condition_template = factory.SubFactory("world.conditions.factories.ConditionTemplateFactory")


def wire_covenant_rite_content() -> CovenantRite:
    """Idempotent seed helper: create the Renew the Oath ritual + CovenantRite row.

    Also seeds the default and role/level-band stat packages (#753 Task 10):
    - Default package ("Oathbound Resolve"): willpower + composure + stability,
      each with value=5, scales_with_severity=True.
    - Sword (offense): "Oathbound Fury I" (strength, presence) at level 1+;
      "Oathbound Fury II" (strength, presence, wits) at level 4+.
    - Shield (defense): "Oathbound Bulwark" (stability, stamina) at level 1+.
    - Crown (support): "Oathbound Grace" (composure, charm) at level 1+.
    All effect rows use scales_with_severity=True.

    Safe to call as both integration-test setUp and staff/seed scripts — uses
    get_or_create semantics at each step so no duplicate rows are created.

    Returns the CovenantRite instance (whether newly created or already present).
    """
    from world.magic.constants import ParticipationRule, RitualExecutionKind
    from world.magic.models import Ritual

    ritual, _ = Ritual.objects.get_or_create(
        name="Renew the Oath",
        defaults={
            "description": (
                "A covenant rite performed by engaged members in the heat of battle. "
                "By reaffirming their sacred oath together, participants renew the bond "
                "that grants them supernatural resolve."
            ),
            "narrative_prose": (
                "The members of the covenant gather, voices joined in the words they swore at "
                "formation. The oath-magic stirs between them, recognising the bond that was "
                "forged in blood and will. As the last word falls, a wave of clarity and "
                "purpose settles over each participant — Oathbound Resolve, the covenant's gift "
                "to those who honour its demands."
            ),
            "execution_kind": RitualExecutionKind.SERVICE,
            "service_function_path": "world.covenants.services.perform_covenant_rite",
            "flow": None,
            "participation_rule": ParticipationRule.FORMATION,
        },
    )

    from world.conditions.factories import (
        OathboundBulwarkConditionFactory,
        OathboundFuryIConditionFactory,
        OathboundFuryIIConditionFactory,
        OathboundGraceConditionFactory,
        OathboundResolveConditionFactory,
    )
    from world.conditions.models import ConditionModifierEffect
    from world.mechanics.models import ModifierCategory, ModifierTarget

    # ------------------------------------------------------------------
    # Ensure the 'stat' ModifierCategory and the named stat targets exist.
    # All pattern: get_or_create keyed on (category, name) so repeated
    # calls never produce duplicates.
    # ------------------------------------------------------------------
    stat_cat, _ = ModifierCategory.objects.get_or_create(
        name="stat",
        defaults={"description": "Primary character statistics.", "display_order": 10},
    )

    def _stat(name: str) -> ModifierTarget:
        target, _ = ModifierTarget.objects.get_or_create(
            category=stat_cat,
            name=name,
            defaults={
                "description": f"{name.capitalize()} stat modifier target.",
                "is_active": True,
            },
        )
        return target

    # ------------------------------------------------------------------
    # Default condition ("Oathbound Resolve") + its modifier effects.
    # ------------------------------------------------------------------
    default_condition = OathboundResolveConditionFactory()

    for stat_name in ("willpower", "composure", "stability"):
        target = _stat(stat_name)
        ConditionModifierEffect.objects.get_or_create(
            condition=default_condition,
            modifier_target=target,
            stage=None,
            defaults={"value": 5, "scales_with_severity": True},
        )

    # ------------------------------------------------------------------
    # CovenantRite row (keyed on ritual; idempotent).
    # ------------------------------------------------------------------
    rite, _ = CovenantRite.objects.get_or_create(
        ritual=ritual,
        defaults={
            "granted_condition": default_condition,
            "covenant_type": CovenantType.DURANCE,
            "min_covenant_level": 2,
            "min_members_present": 2,
            "base_severity": 2,
            "severity_per_extra_participant": 1,
            "max_severity": None,
            "duration_rounds": None,
        },
    )

    # ------------------------------------------------------------------
    # Canonical DURANCE roles (get_or_create on slug, mirroring the
    # pattern in integration_tests/game_content/items.py).
    # ------------------------------------------------------------------
    sword_role, _ = CovenantRole.objects.get_or_create(
        slug="sword-vanguard",
        defaults={
            "name": "Vanguard",
            "covenant_type": CovenantType.DURANCE,
            "archetype": RoleArchetype.SWORD,
            "speed_rank": 2,
        },
    )
    shield_role, _ = CovenantRole.objects.get_or_create(
        slug="shield-bulwark",
        defaults={
            "name": "Bulwark",
            "covenant_type": CovenantType.DURANCE,
            "archetype": RoleArchetype.SHIELD,
            "speed_rank": 3,
        },
    )
    crown_role, _ = CovenantRole.objects.get_or_create(
        slug="crown-luminary",
        defaults={
            "name": "Luminary",
            "covenant_type": CovenantType.DURANCE,
            "archetype": RoleArchetype.CROWN,
            "speed_rank": 1,
        },
    )

    # ------------------------------------------------------------------
    # Role-package conditions + modifier effects.
    # ------------------------------------------------------------------

    # Sword level-1 band: strength, presence
    fury_i = OathboundFuryIConditionFactory()
    for stat_name in ("strength", "presence"):
        ConditionModifierEffect.objects.get_or_create(
            condition=fury_i,
            modifier_target=_stat(stat_name),
            stage=None,
            defaults={"value": 5, "scales_with_severity": True},
        )

    # Sword level-4 band: strength, presence, wits
    fury_ii = OathboundFuryIIConditionFactory()
    for stat_name in ("strength", "presence", "wits"):
        ConditionModifierEffect.objects.get_or_create(
            condition=fury_ii,
            modifier_target=_stat(stat_name),
            stage=None,
            defaults={"value": 7, "scales_with_severity": True},
        )

    # Shield level-1 band: stability, stamina
    bulwark = OathboundBulwarkConditionFactory()
    for stat_name in ("stability", "stamina"):
        ConditionModifierEffect.objects.get_or_create(
            condition=bulwark,
            modifier_target=_stat(stat_name),
            stage=None,
            defaults={"value": 5, "scales_with_severity": True},
        )

    # Crown level-1 band: composure, charm
    grace = OathboundGraceConditionFactory()
    for stat_name in ("composure", "charm"):
        ConditionModifierEffect.objects.get_or_create(
            condition=grace,
            modifier_target=_stat(stat_name),
            stage=None,
            defaults={"value": 5, "scales_with_severity": True},
        )

    # ------------------------------------------------------------------
    # CovenantRiteRolePackage rows (get_or_create on the unique triple).
    # ------------------------------------------------------------------
    CovenantRiteRolePackage.objects.get_or_create(
        rite=rite,
        covenant_role=sword_role,
        min_covenant_level=1,
        defaults={"condition_template": fury_i},
    )
    CovenantRiteRolePackage.objects.get_or_create(
        rite=rite,
        covenant_role=sword_role,
        min_covenant_level=4,
        defaults={"condition_template": fury_ii},
    )
    CovenantRiteRolePackage.objects.get_or_create(
        rite=rite,
        covenant_role=shield_role,
        min_covenant_level=1,
        defaults={"condition_template": bulwark},
    )
    CovenantRiteRolePackage.objects.get_or_create(
        rite=rite,
        covenant_role=crown_role,
        min_covenant_level=1,
        defaults={"condition_template": grace},
    )

    return rite


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
