"""FactoryBoy factories for check system tests."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import factory
from factory.django import DjangoModelFactory

from actions.models import ConsequencePool, ConsequencePoolEntry
from world.checks.models import (
    CheckCategory,
    CheckType,
    CheckTypeAspect,
    CheckTypeSpecialization,
    CheckTypeTrait,
    Consequence,
    ConsequenceEffect,
)

if TYPE_CHECKING:
    from actions.models.action_templates import ActionTemplate


class CheckCategoryFactory(DjangoModelFactory):
    class Meta:
        model = CheckCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"CheckCategory{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class CheckTypeFactory(DjangoModelFactory):
    class Meta:
        model = CheckType
        django_get_or_create = ("name", "category")

    name = factory.Sequence(lambda n: f"CheckType{n}")
    category = factory.SubFactory(CheckCategoryFactory)
    description = factory.Faker("sentence")
    is_active = True
    display_order = factory.Sequence(lambda n: n)


class CheckTypeTraitFactory(DjangoModelFactory):
    class Meta:
        model = CheckTypeTrait

    check_type = factory.SubFactory(CheckTypeFactory)
    trait = None  # Must be provided by caller
    weight = Decimal("1.0")


class CheckTypeSpecializationFactory(DjangoModelFactory):
    class Meta:
        model = CheckTypeSpecialization

    check_type = factory.SubFactory(CheckTypeFactory)
    specialization = None  # Must be provided by caller (a skills.Specialization)
    weight = Decimal("1.0")


class CheckTypeAspectFactory(DjangoModelFactory):
    class Meta:
        model = CheckTypeAspect

    check_type = factory.SubFactory(CheckTypeFactory)
    aspect = None  # Must be provided by caller
    weight = Decimal("1.0")


class ConsequenceFactory(DjangoModelFactory):
    """Factory for creating Consequence instances."""

    class Meta:
        model = Consequence

    outcome_tier = factory.SubFactory("world.traits.factories.CheckOutcomeFactory")
    label = factory.Sequence(lambda n: f"Consequence{n}")
    mechanical_description = factory.Faker("sentence")
    weight = 1
    character_loss = False


class ConsequenceEffectFactory(DjangoModelFactory):
    """Factory for creating ConsequenceEffect instances."""

    class Meta:
        model = ConsequenceEffect

    consequence = factory.SubFactory(ConsequenceFactory)
    effect_type = "apply_condition"
    execution_order = 0
    target = "self"


# ---------------------------------------------------------------------------
# Social check type + action template helpers
# ---------------------------------------------------------------------------

# (check_type_name, description, display_order)
_SOCIAL_CHECK_TYPES = [
    ("Intimidation", "Coercing through force of presence, threats, or physical dominance.", 0),
    ("Persuasion", "Convincing through reasoned argument, charm, and social grace.", 1),
    ("Deceive", "Misleading through misdirection, half-truths, or outright lies.", 2),
    ("Seduction", "Beguiling through charm, allure, and romantic suggestion.", 3),
    ("Performance", "Captivating an audience through music, oration, or storytelling.", 4),
    ("Presence", "Commanding attention through sheer force of personality.", 5),
]

# (check_type_name, trait_name, weight) — placeholder stat weights
_SOCIAL_TRAIT_WEIGHTS = [
    ("Intimidation", "presence", "1.00"),
    ("Intimidation", "strength", "0.50"),
    ("Persuasion", "charm", "1.00"),
    ("Persuasion", "intellect", "0.50"),
    ("Deceive", "wits", "1.00"),
    ("Deceive", "charm", "0.50"),
    ("Seduction", "charm", "1.00"),
    ("Seduction", "presence", "0.50"),
    ("Performance", "presence", "1.00"),
    ("Performance", "charm", "0.50"),
    ("Presence", "presence", "1.00"),
    ("Presence", "willpower", "0.50"),
]

# (template_name, check_type_name, target_type, icon)
_SOCIAL_ACTION_TEMPLATES = [
    ("Intimidate", "Intimidation", "single", "skull"),
    ("Persuade", "Persuasion", "single", "handshake"),
    ("Deceive", "Deceive", "single", "mask"),
    ("Flirt", "Seduction", "single", "heart"),
    ("Perform", "Performance", "area", "music"),
    ("Entrance", "Presence", "area", "sparkles"),
]

# Template name for the Entrance social action — grants entry flourish resonance.
_ENTRANCE_TEMPLATE_NAME = "Entrance"

# Pool name prefix for social consequence pools.
_SOCIAL_POOL_PREFIX = "Social"

# CheckOutcome tier names used in consequence pool entries.
_OUTCOME_FAILURE = "Failure"
_OUTCOME_PARTIAL = "Partial Success"
_OUTCOME_SUCCESS = "Success"

# (action_name, outcome_tier_name, label, weight)
_SOCIAL_POOL_CONSEQUENCES: dict[str, list[tuple[str, str, int]]] = {
    "Intimidate": [
        (_OUTCOME_FAILURE, "Intimidation falls flat", 1),
        (_OUTCOME_PARTIAL, "Target rattled but holds firm", 2),
        (_OUTCOME_SUCCESS, "Target cowed and compliant", 1),
    ],
    "Persuade": [
        (_OUTCOME_FAILURE, "Argument dismissed outright", 1),
        (_OUTCOME_PARTIAL, "Target intrigued but unconvinced", 2),
        (_OUTCOME_SUCCESS, "Target fully persuaded", 1),
    ],
    "Deceive": [
        (_OUTCOME_FAILURE, "Lie detected immediately", 1),
        (_OUTCOME_PARTIAL, "Partial deception holds", 2),
        (_OUTCOME_SUCCESS, "Target completely deceived", 1),
    ],
    "Flirt": [
        (_OUTCOME_FAILURE, "Advance rebuffed", 1),
        (_OUTCOME_PARTIAL, "Interest piqued but guarded", 2),
        (_OUTCOME_SUCCESS, "Charm lands completely", 1),
    ],
    "Perform": [
        (_OUTCOME_FAILURE, "Performance falls flat", 1),
        (_OUTCOME_PARTIAL, "Audience politely attentive", 2),
        (_OUTCOME_SUCCESS, "Audience captivated", 1),
    ],
    "Entrance": [
        (_OUTCOME_FAILURE, "Entrance goes unnoticed", 1),
        (_OUTCOME_PARTIAL, "Attention caught briefly", 2),
        (_OUTCOME_SUCCESS, "All eyes arrested", 1),
    ],
}


# (check_type_name, description, display_order)
_RESISTANCE_CHECK_TYPES = [
    ("Composure", "Resisting social pressure through force of will.", 0),
]

# (check_type_name, trait_name, weight)
# "willpower" matches the existing social trait already seeded by _SOCIAL_TRAIT_WEIGHTS.
_RESISTANCE_TRAIT_WEIGHTS = [
    ("Composure", "willpower", "1.00"),
]


def create_resistance_check_types() -> dict[str, CheckType]:
    """Create resistance CheckTypes (e.g. Composure) under the Social category.

    Composure represents a defender's capacity to resist social influence through
    force of will.  It is placed in the existing ``Social`` CheckCategory so
    resistance checks share the same organisational grouping as the social
    actions that trigger them.

    Uses the same ``willpower`` stat trait already referenced by social
    check-type weights — no new trait name is introduced.

    Self-contained and idempotent — safe to call multiple times.

    Returns:
        Dict mapping check type name to CheckType instance.
    """
    from world.traits.factories import StatTraitFactory

    social_cat = CheckCategoryFactory(
        name="Social",
        description="Checks involving social interaction, persuasion, and presence.",
        display_order=10,
    )

    check_types: dict[str, CheckType] = {}
    for name, description, display_order in _RESISTANCE_CHECK_TYPES:
        check_types[name] = CheckTypeFactory(
            name=name,
            category=social_cat,
            description=description,
            display_order=display_order,
        )

    for ct_name, trait_name, weight in _RESISTANCE_TRAIT_WEIGHTS:
        trait = StatTraitFactory(name=trait_name)
        CheckTypeTrait.objects.get_or_create(
            check_type=check_types[ct_name],
            trait=trait,
            defaults={"weight": Decimal(weight)},
        )

    return check_types


def create_social_check_types() -> dict[str, CheckType]:
    """Create the Social CheckCategory, 6 CheckTypes, and placeholder trait weights.

    Self-contained: creates any missing stat traits via StatTraitFactory.
    Uses get_or_create throughout — safe to call multiple times.

    Returns:
        Dict mapping check type name to CheckType instance.
    """
    from world.traits.factories import StatTraitFactory

    social_cat = CheckCategoryFactory(
        name="Social",
        description="Checks involving social interaction, persuasion, and presence.",
        display_order=10,
    )

    check_types: dict[str, CheckType] = {}
    for name, description, display_order in _SOCIAL_CHECK_TYPES:
        check_types[name] = CheckTypeFactory(
            name=name,
            category=social_cat,
            description=description,
            display_order=display_order,
        )

    for ct_name, trait_name, weight in _SOCIAL_TRAIT_WEIGHTS:
        trait = StatTraitFactory(name=trait_name)
        CheckTypeTrait.objects.get_or_create(
            check_type=check_types[ct_name],
            trait=trait,
            defaults={"weight": Decimal(weight)},
        )

    return check_types


def create_social_action_templates() -> list[ActionTemplate]:
    """Create social ActionTemplates linked to social CheckTypes and ConsequencePools.

    Calls create_social_check_types() and create_social_consequence_pools() first.
    Uses get_or_create — safe to call multiple times.

    Returns:
        List of created ActionTemplate instances.
    """
    from actions.factories import ActionTemplateFactory

    check_types = create_social_check_types()
    pools = create_social_consequence_pools()

    templates: list[ActionTemplate] = []
    for name, ct_name, target_type, icon in _SOCIAL_ACTION_TEMPLATES:
        grants_entry_flourish = name == _ENTRANCE_TEMPLATE_NAME
        template = ActionTemplateFactory(
            name=name,
            check_type=check_types[ct_name],
            consequence_pool=pools[name],
            target_type=target_type,
            icon=icon,
            category="social",
            grants_entry_flourish=grants_entry_flourish,
        )
        # django_get_or_create won't update consequence_pool on existing rows;
        # ensure it is wired even when the template already existed.
        if template.consequence_pool_id != pools[name].pk:
            template.consequence_pool = pools[name]
            template.save(update_fields=["consequence_pool"])
        templates.append(template)

    return templates


def create_social_consequence_pools() -> dict[str, ConsequencePool]:
    """Create one ConsequencePool per social action, each seeded with 3 Consequences.

    Pools are named ``"Social: <ActionName>"``.  Consequences are linked to
    standard CheckOutcome tiers ("Failure", "Partial Success", "Success").

    Safe to call multiple times — uses get_or_create throughout.

    Returns:
        Dict mapping action name (e.g. ``"Intimidate"``) to its ConsequencePool.
    """
    from world.traits.factories import CheckOutcomeFactory

    pools: dict[str, ConsequencePool] = {}

    for action_name, consequence_specs in _SOCIAL_POOL_CONSEQUENCES.items():
        pool_name = f"{_SOCIAL_POOL_PREFIX}: {action_name}"
        pool, _ = ConsequencePool.objects.get_or_create(
            name=pool_name,
            defaults={"description": f"Consequence pool for {action_name} social action."},
        )
        pools[action_name] = pool

        for outcome_name, label, weight in consequence_specs:
            outcome = CheckOutcomeFactory(name=outcome_name)
            consequence, _ = Consequence.objects.get_or_create(
                outcome_tier=outcome,
                label=label,
                defaults={"weight": weight, "character_loss": False},
            )
            ConsequencePoolEntry.objects.get_or_create(
                pool=pool,
                consequence=consequence,
                defaults={"weight_override": None, "is_excluded": False},
            )

    return pools
