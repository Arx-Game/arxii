"""
Factory definitions for species system tests.
"""

from typing import TYPE_CHECKING

import factory
import factory.django as factory_django

from world.magic.constants import GiftKind
from world.species.models import Language, Species, SpeciesGiftGrant, SpeciesStatBonus

if TYPE_CHECKING:
    from world.conditions.models import ConditionTemplate


class LanguageFactory(factory_django.DjangoModelFactory):
    """Factory for creating Language instances."""

    class Meta:
        model = Language
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"TestLanguage{n}")
    description = factory.LazyAttribute(
        lambda obj: f"The {obj.name} language",
    )


class SpeciesFactory(factory_django.DjangoModelFactory):
    """Factory for creating Species instances."""

    class Meta:
        model = Species
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"TestSpecies{n}")
    description = factory.LazyAttribute(
        lambda obj: f"Description of the {obj.name} species",
    )
    parent = None
    sort_order = 0


class SubspeciesFactory(SpeciesFactory):
    """Factory for creating subspecies (Species with a parent)."""

    parent = factory.SubFactory(SpeciesFactory)
    name = factory.Sequence(lambda n: f"TestSubspecies{n}")
    description = factory.LazyAttribute(
        lambda obj: f"Description of the {obj.name} subspecies of {obj.parent.name}",
    )


class SpeciesStatBonusFactory(factory_django.DjangoModelFactory):
    """Factory for creating SpeciesStatBonus instances."""

    class Meta:
        model = SpeciesStatBonus

    species = factory.SubFactory(SpeciesFactory)
    stat = "strength"
    value = 1


class SpeciesGiftGrantFactory(factory_django.DjangoModelFactory):
    """Factory for creating SpeciesGiftGrant instances (kind=MINOR enforced by clean())."""

    class Meta:
        model = SpeciesGiftGrant

    species = factory.SubFactory(SpeciesFactory)
    gift = factory.SubFactory("world.magic.factories.GiftFactory", kind=GiftKind.MINOR)
    drawback_condition = None


# ---------------------------------------------------------------------------
# Sunlight Exposure condition + radiant DoT seed (#1588)
# ---------------------------------------------------------------------------

SUNLIGHT_EXPOSURE_NAME = "Sunlight Exposure"
SUNLIGHT_EXPOSURE_DAMAGE = 5


def ensure_sunlight_exposure_content() -> "ConditionTemplate":
    """Idempotently seed the Sunlight Exposure condition template + radiant DoT (#1588).

    The template carries a ``ConditionDamageOverTime`` (radiant) so the existing
    ``_process_round_tick`` machinery applies sunlight damage through the peril
    pipeline exactly like poison/Burning — no new tick machinery. Exposure gating
    (outdoor + day-phase) and round-ensurance are applied by
    ``reconcile_sunlight_exposure`` in ``world.species.services``.

    Returns:
        The (get-or-created) Sunlight Exposure ConditionTemplate.
    """
    from world.conditions.factories import ensure_radiant_damage_type
    from world.conditions.models import (
        ConditionCategory,
        ConditionDamageOverTime,
        ConditionTemplate,
    )

    radiant = ensure_radiant_damage_type()
    category, _created = ConditionCategory.objects.get_or_create(
        name="Environmental",
        defaults={"description": "Environmental hazard conditions (#1588)."},
    )
    template, _created = ConditionTemplate.objects.get_or_create(
        name=SUNLIGHT_EXPOSURE_NAME,
        defaults={
            "category": category,
            "description": "Sunlight exposure harming a sunlight-vulnerable being (#1588).",
            "player_description": "You are exposed to sunlight.",
            "observer_description": "is exposed to sunlight.",
        },
    )
    ConditionDamageOverTime.objects.update_or_create(
        condition=template,
        stage=None,
        damage_type=radiant,
        defaults={"base_damage": SUNLIGHT_EXPOSURE_DAMAGE},
    )
    return template
