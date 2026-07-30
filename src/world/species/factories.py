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
    drawback_distinction = None
    cg_point_cost = 0


# ---------------------------------------------------------------------------
# Sunlight Exposure condition + radiant DoT seed (#1588, staged #2846)
# ---------------------------------------------------------------------------

SUNLIGHT_EXPOSURE_NAME = "Sunlight Exposure"
SUNLIGHT_EXPOSURE_DAMAGE = 5
SUNLIGHT_SEARING_DAMAGE = 10
SUNLIGHT_STAGE_DISCOMFORT = "Sun-Struck"
SUNLIGHT_STAGE_BURNING = "Burning"
SUNLIGHT_STAGE_SEARING = "Searing"
# PLACEHOLDER: every check suffers this per point of severity while exposed.
SUNLIGHT_CHECK_PENALTY_PER_SEVERITY = -1


def ensure_sunlight_exposure_content() -> "ConditionTemplate":
    """Idempotently seed the Sunlight Exposure condition template + radiant DoT (#1588).

    The template carries a ``ConditionDamageOverTime`` (radiant) so the existing
    ``_process_round_tick`` machinery applies sunlight damage through the peril
    pipeline exactly like poison — no new tick machinery. Exposure gating
    (outdoor + day-phase) and round-ensurance are applied by
    ``reconcile_sunlight_exposure`` in ``world.species.services``.

    ``tick_timing=END_OF_ROUND`` (#1744): matches poison's established convention
    (``world.conditions.services.ensure_poison_content``). END_OF_ROUND is also the
    model field's default as of #1762 (it was ``START_OF_ROUND`` when this was
    written, which is why the explicit set mattered). START-timing DoTs tick during combat's
    DECLARING phase (``begin_declaration_phase``) and are never reached at all by
    non-combat ``resolve_scene_round`` (which only ever ticks ``timing="end"``);
    Succor's cover window is also RESOLVING-gated
    (``CombatRoundContext.get_cover_for`` / ``SceneRoundContext.get_cover_for``),
    so only an END-timing DoT can be protected by Succor or ticked through the
    real non-combat scene-round path.

    Returns:
        The (get-or-created) Sunlight Exposure ConditionTemplate.
    """
    from decimal import Decimal

    from world.conditions.constants import DamageTickTiming
    from world.conditions.factories import ensure_radiant_damage_type
    from world.conditions.models import (
        ConditionCategory,
        ConditionCheckModifier,
        ConditionDamageOverTime,
        ConditionStage,
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
            "has_progression": True,
        },
    )
    if not template.has_progression:
        # Pre-#2846 rows lack the flag; apply_condition only assigns a first
        # stage when it's set, so the staged model depends on it.
        template.has_progression = True
        template.save(update_fields=["has_progression"])
    # #2846: severity-driven stages. Below BURNING_SEVERITY_THRESHOLD the condition
    # only impairs (check penalties, scaling with severity); the damaging stages carry
    # their own DoT rows, so damage exists ONLY at Burning+ — the acute round tick's
    # stage-filter (Q(stage=instance.current_stage)) does the gating for free.
    from world.species.sun_constants import (
        BURNING_SEVERITY_THRESHOLD,
        SEARING_SEVERITY_THRESHOLD,
    )

    ConditionStage.objects.update_or_create(
        condition=template,
        stage_order=1,
        defaults={
            "name": SUNLIGHT_STAGE_DISCOMFORT,
            "description": "PLACEHOLDER: the sun bites; nothing burns yet.",
            "severity_threshold": 1,
            "severity_multiplier": Decimal("1.00"),
        },
    )
    burning, _created = ConditionStage.objects.update_or_create(
        condition=template,
        stage_order=2,
        defaults={
            "name": SUNLIGHT_STAGE_BURNING,
            "description": "PLACEHOLDER: exposed skin blisters under direct sun.",
            "severity_threshold": BURNING_SEVERITY_THRESHOLD,
            "severity_multiplier": Decimal("1.00"),
        },
    )
    searing, _created = ConditionStage.objects.update_or_create(
        condition=template,
        stage_order=3,
        defaults={
            "name": SUNLIGHT_STAGE_SEARING,
            "description": "PLACEHOLDER: the sun sears unprotected flesh.",
            "severity_threshold": SEARING_SEVERITY_THRESHOLD,
            "severity_multiplier": Decimal("1.00"),
        },
    )
    # Fixed per-stage damage (scales_with_severity/stacks off): predictable, never
    # instantaneously lethal — escalation happens by *stage*, not multiplication.
    ConditionDamageOverTime.objects.filter(condition=template, stage__isnull=True).delete()
    for stage, damage in ((burning, SUNLIGHT_EXPOSURE_DAMAGE), (searing, SUNLIGHT_SEARING_DAMAGE)):
        ConditionDamageOverTime.objects.update_or_create(
            stage=stage,
            condition=None,
            damage_type=radiant,
            defaults={
                "base_damage": damage,
                "tick_timing": DamageTickTiming.END_OF_ROUND,
                "scales_with_severity": False,
                "scales_with_stacks": False,
            },
        )
    # Severity-scaled impairment on every check category that exists (template-level,
    # so it applies at every stage including mere discomfort).
    from world.checks.models import CheckCategory

    for check_category in CheckCategory.objects.all():
        ConditionCheckModifier.objects.update_or_create(
            condition=template,
            stage=None,
            check_category=check_category,
            check_type=None,
            defaults={
                "modifier_value": SUNLIGHT_CHECK_PENALTY_PER_SEVERITY,
                "scales_with_severity": True,
            },
        )
    return template


def ensure_sunlight_distinctions() -> tuple:
    """Idempotently seed the Bane/Allergy: Sunlight distinctions (#2846).

    The Distinction rows are the single mechanical anchor for sun sensitivity
    (ADR pending; #2752 tag pattern): species stamp them innately via
    ``SpeciesGiftGrant.drawback_distinction``, other species may take one in CG
    for reimbursement (negative ``cost_per_rank``), and
    ``world.species.sun_sensitivity.sun_sensitivity_for`` resolves the held
    tier by ``DistinctionTag`` — never by slug or name string.

    Returns:
        ``(bane, allergy)`` Distinction rows.
    """
    from world.distinctions.models import (
        Distinction,
        DistinctionCategory,
        DistinctionTag,
    )
    from world.species.sun_constants import (
        SUN_ALLERGY_CG_COST,
        SUN_ALLERGY_SLUG,
        SUN_ALLERGY_TAG,
        SUN_BANE_CG_COST,
        SUN_BANE_SLUG,
        SUN_BANE_TAG,
    )

    category, _created = DistinctionCategory.objects.get_or_create(
        slug="drawbacks",
        defaults={
            "name": "Drawbacks",
            "description": "PLACEHOLDER: disadvantages that reimburse CG points.",
        },
    )
    bane_tag, _created = DistinctionTag.objects.get_or_create(
        slug=SUN_BANE_TAG, defaults={"name": "Sun Bane"}
    )
    allergy_tag, _created = DistinctionTag.objects.get_or_create(
        slug=SUN_ALLERGY_TAG, defaults={"name": "Sun Allergy"}
    )
    bane, _created = Distinction.objects.get_or_create(
        slug=SUN_BANE_SLUG,
        defaults={
            "name": "Bane: Sunlight",
            "description": (
                "PLACEHOLDER: direct sunlight is anathema — without heavy precautions "
                "it burns, and even covered you are diminished under the open sky."
            ),
            "category": category,
            "cost_per_rank": SUN_BANE_CG_COST,
            "max_rank": 1,
        },
    )
    allergy, _created = Distinction.objects.get_or_create(
        slug=SUN_ALLERGY_SLUG,
        defaults={
            "name": "Allergy: Sunlight",
            "description": (
                "PLACEHOLDER: direct sunlight sickens you — cover up or keep to the "
                "shade, or it will do far worse than sicken."
            ),
            "category": category,
            "cost_per_rank": SUN_ALLERGY_CG_COST,
            "max_rank": 1,
        },
    )
    bane.tags.add(bane_tag)
    allergy.tags.add(allergy_tag)
    bane.mutually_exclusive_with.add(allergy)
    return bane, allergy


def ensure_appetite_distinctions() -> tuple:
    """Idempotently seed the Appetite: Blood / Appetite: Essence distinctions (#2853).

    Tag-identified anchors (ADR-0179 pattern): species stamp them innately via
    ``SpeciesGiftGrant.drawback_distinction``; the Shade condition grants
    Essence on application. Cost 0 — the appetite's price is the economy
    (no natural regen, upkeep drains), not CG points.

    Returns:
        ``(blood, essence)`` Distinction rows.
    """
    from world.distinctions.models import (
        Distinction,
        DistinctionCategory,
        DistinctionTag,
    )
    from world.species.appetites import (
        APPETITE_BLOOD_SLUG,
        APPETITE_BLOOD_TAG,
        APPETITE_ESSENCE_SLUG,
        APPETITE_ESSENCE_TAG,
    )

    category, _created = DistinctionCategory.objects.get_or_create(
        slug="drawbacks",
        defaults={
            "name": "Drawbacks",
            "description": "PLACEHOLDER: disadvantages that reimburse CG points.",
        },
    )
    blood_tag, _created = DistinctionTag.objects.get_or_create(
        slug=APPETITE_BLOOD_TAG, defaults={"name": "Blood Appetite"}
    )
    essence_tag, _created = DistinctionTag.objects.get_or_create(
        slug=APPETITE_ESSENCE_TAG, defaults={"name": "Essence Appetite"}
    )
    blood, _created = Distinction.objects.get_or_create(
        slug=APPETITE_BLOOD_SLUG,
        defaults={
            "name": "Appetite: Blood",
            "description": (
                "PLACEHOLDER: living blood sustains you — anima comes from the "
                "bite, never from rest."
            ),
            "category": category,
            "cost_per_rank": 0,
            "max_rank": 1,
        },
    )
    essence, _created = Distinction.objects.get_or_create(
        slug=APPETITE_ESSENCE_SLUG,
        defaults={
            "name": "Appetite: Essence",
            "description": (
                "PLACEHOLDER: the living warmth of others sustains you — anima "
                "comes through touch and glamour, never from rest."
            ),
            "category": category,
            "cost_per_rank": 0,
            "max_rank": 1,
        },
    )
    blood.tags.add(blood_tag)
    essence.tags.add(essence_tag)
    return blood, essence


def ensure_ravenous_condition() -> "ConditionTemplate":
    """Idempotently seed the Ravenous hunger condition (#2853).

    Severity tracks hunger depth (``world.magic.services.appetites.hunger_severity``);
    visible to observers (the hunger tell) and the driver of feeding restraint
    checks. Check penalties are a PLACEHOLDER author pass.
    """
    from world.conditions.models import ConditionCategory, ConditionTemplate
    from world.species.appetites import RAVENOUS_NAME

    category, _created = ConditionCategory.objects.get_or_create(
        name="Social",
        defaults={"description": "Social conditions."},
    )
    template, _created = ConditionTemplate.objects.get_or_create(
        name=RAVENOUS_NAME,
        defaults={
            "category": category,
            "description": "PLACEHOLDER: gnawing hunger for blood or essence (#2853).",
            "player_description": "Hunger gnaws at you.",
            "observer_description": "looks hollow-eyed and hungry.",
            "is_visible_to_others": True,
        },
    )
    return template


def ensure_appetite_upkeep() -> None:
    """Idempotently seed the appetite upkeep configs (#2853, PLACEHOLDER magnitudes).

    Blood appetite (vampires' anchor): weekly -1, floor 10% of maximum.
    Essence appetite: no upkeep by default — the Shade condition's daily -1 /
    floor 0 config rides its own distinction wiring at Shade content time (the
    half-living tiers' ruled penalty is no-regen only).
    """
    from world.magic.models.appetites import AppetitePeriod, AppetiteUpkeep

    blood, _essence = ensure_appetite_distinctions()
    AppetiteUpkeep.objects.get_or_create(
        distinction=blood,
        defaults={
            "period": AppetitePeriod.WEEKLY,
            "amount": 1,
            "floor_percent": 10,
        },
    )
