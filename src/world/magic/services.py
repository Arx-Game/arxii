"""
Magic system service functions.

This module provides service functions for the magic system, including
calculations for aura percentages based on affinity and resonance totals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.models import CharacterAnima, CharacterResonanceTotal
from world.magic.types import (
    AffinityType,
    AnimaCostResult,
    AuraPercentages,
    OverburnSeverity,
    RuntimeTechniqueStats,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.objects.models import ObjectDB

    from world.magic.models import Resonance as ResonanceModel, Technique


def calculate_affinity_breakdown(resonances: QuerySet[ResonanceModel]) -> dict[str, int]:
    """Derive affinity counts from a set of resonances.

    Args:
        resonances: QuerySet of Resonance instances.

    Returns:
        Dict mapping affinity name to count of resonances with that affinity.
    """
    counts: dict[str, int] = {}
    for resonance in resonances.select_related("affinity").all():
        aff_name = resonance.affinity.name
        counts[aff_name] = counts.get(aff_name, 0) + 1
    return counts


def add_resonance_total(character_sheet, resonance: ResonanceModel, amount: int) -> None:
    """
    Add to a character's resonance total.

    Creates the CharacterResonanceTotal if it doesn't exist.

    Args:
        character_sheet: CharacterSheet instance
        resonance: Resonance instance
        amount: Amount to add (can be negative)
    """
    total, created = CharacterResonanceTotal.objects.get_or_create(
        character=character_sheet,
        resonance=resonance,
        defaults={"total": amount},
    )
    if not created:
        # Use select_for_update to prevent race conditions with SharedMemoryModel
        with transaction.atomic():
            total = CharacterResonanceTotal.objects.select_for_update().get(pk=total.pk)
            total.total += amount
            total.save()


def get_aura_percentages(character_sheet) -> AuraPercentages:
    """
    Calculate aura percentages from affinity and resonance totals.

    The aura represents a character's soul-state across the three magical
    affinities (Celestial, Primal, Abyssal). Percentages are calculated from:
    1. Direct affinity totals (CharacterAffinityTotal)
    2. Resonance contributions (CharacterResonanceTotal via resonance.affinity)

    Args:
        character_sheet: A CharacterSheet instance with related affinity_totals
                        and resonance_totals. For optimal performance when
                        calling in a loop, prefetch affinity_totals__affinity
                        and resonance_totals__resonance__affinity.

    Returns:
        AuraPercentages dataclass with celestial, primal, abyssal percentages
        (floats summing to 100). If no totals exist, returns an even split.
    """
    # Initialize affinity totals
    affinity_totals = {
        AffinityType.CELESTIAL: 0,
        AffinityType.PRIMAL: 0,
        AffinityType.ABYSSAL: 0,
    }

    # Get direct affinity totals
    for at in character_sheet.affinity_totals.select_related("affinity"):
        aff_name = at.affinity.name.lower()
        if aff_name in affinity_totals:
            affinity_totals[aff_name] = at.total

    # Add resonance contributions via affinity
    for rt in character_sheet.resonance_totals.select_related("resonance__affinity"):
        affinity_name = rt.resonance.affinity.name.lower()
        if affinity_name in [
            AffinityType.CELESTIAL,
            AffinityType.PRIMAL,
            AffinityType.ABYSSAL,
        ]:
            affinity_totals[affinity_name] += rt.total

    # Calculate percentages
    grand_total = sum(affinity_totals.values())
    if grand_total == 0:
        return AuraPercentages(celestial=33.33, primal=33.33, abyssal=33.34)

    return AuraPercentages(
        celestial=(affinity_totals[AffinityType.CELESTIAL] / grand_total) * 100,
        primal=(affinity_totals[AffinityType.PRIMAL] / grand_total) * 100,
        abyssal=(affinity_totals[AffinityType.ABYSSAL] / grand_total) * 100,
    )


def get_runtime_technique_stats(
    technique: Technique,
    character: ObjectDB | None,  # noqa: ARG001 — future: affinity bonuses, Audere modifiers
) -> RuntimeTechniqueStats:
    """Calculate runtime intensity and control for a technique.

    MVP: returns base values. Future scope #2 adds affinity bonuses,
    combat escalation, social scene safety, and Audere modifiers.
    """
    return RuntimeTechniqueStats(
        intensity=technique.intensity,
        control=technique.control,
    )


def calculate_effective_anima_cost(
    *,
    base_cost: int,
    runtime_intensity: int,
    runtime_control: int,
    current_anima: int,
) -> AnimaCostResult:
    """Calculate effective anima cost using the delta formula.

    effective_cost = max(base_cost - (control - intensity), 0)
    deficit = max(effective_cost - current_anima, 0)
    """
    control_delta = runtime_control - runtime_intensity
    effective_cost = max(base_cost - control_delta, 0)
    deficit = max(effective_cost - current_anima, 0)

    return AnimaCostResult(
        base_cost=base_cost,
        effective_cost=effective_cost,
        control_delta=control_delta,
        current_anima=current_anima,
        deficit=deficit,
    )


# Severity thresholds — MVP hardcoded, future: authored lookup table
_DEATH_RISK_THRESHOLD = 15
_DANGEROUS_THRESHOLD = 8


def get_overburn_severity(deficit: int) -> OverburnSeverity | None:
    """Classify overburn severity from anima deficit.

    Returns None if no overburn (deficit <= 0).
    """
    if deficit <= 0:
        return None

    if deficit >= _DEATH_RISK_THRESHOLD:
        return OverburnSeverity(
            label="This can result in character death.",
            can_cause_death=True,
        )
    if deficit >= _DANGEROUS_THRESHOLD:
        return OverburnSeverity(
            label="Dangerous — you will sustain serious magical injuries.",
            can_cause_death=False,
        )
    return OverburnSeverity(
        label="Painful — you will sustain magical injuries.",
        can_cause_death=False,
    )


def deduct_anima(character: ObjectDB, effective_cost: int) -> int:
    """Deduct anima from character, returning the overburn deficit.

    Uses select_for_update inside transaction.atomic for race-condition
    safety, following the ActionPointPool.spend() pattern.
    Returns 0 if no overburn, positive int if life force is drawn.
    """
    if effective_cost <= 0:
        return 0

    with transaction.atomic():
        anima = CharacterAnima.objects.select_for_update().get(character=character)
        deficit = max(effective_cost - anima.current, 0)
        anima.current = max(anima.current - effective_cost, 0)
        anima.save(update_fields=["current"])
    return deficit
