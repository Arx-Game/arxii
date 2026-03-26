"""FactoryBoy factories for check system tests."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import factory
from factory.django import DjangoModelFactory

from world.checks.models import (
    CheckCategory,
    CheckType,
    CheckTypeAspect,
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
    ("Deception", "Misleading through misdirection, half-truths, or outright lies.", 2),
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
    ("Deception", "wits", "1.00"),
    ("Deception", "charm", "0.50"),
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
    ("Deceive", "Deception", "single", "mask"),
    ("Flirt", "Seduction", "single", "heart"),
    ("Perform", "Performance", "area", "music"),
    ("Entrance", "Presence", "area", "sparkles"),
]


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
    """Create social ActionTemplates linked to social CheckTypes.

    Calls create_social_check_types() first to ensure CheckTypes exist.
    Uses get_or_create — safe to call multiple times.

    Returns:
        List of created ActionTemplate instances.
    """
    from actions.factories import ActionTemplateFactory

    check_types = create_social_check_types()

    templates: list[ActionTemplate] = []
    for name, ct_name, target_type, icon in _SOCIAL_ACTION_TEMPLATES:
        template = ActionTemplateFactory(
            name=name,
            check_type=check_types[ct_name],
            consequence_pool=None,
            target_type=target_type,
            icon=icon,
            category="social",
        )
        templates.append(template)

    return templates
