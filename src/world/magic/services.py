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
    MishapResult,
    OverburnSeverity,
    RuntimeTechniqueStats,
    TechniqueUseResult,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from django.db.models import QuerySet
    from evennia.objects.models import ObjectDB

    from actions.models.action_templates import ConsequencePool
    from world.checks.types import CheckResult
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


def select_mishap_pool(control_deficit: int) -> ConsequencePool | None:  # noqa: ARG001
    """Select a mishap consequence pool based on control deficit magnitude.

    Returns None if no mishap pools are authored yet. Future: query
    global mishap pools tiered by deficit range.
    """
    # MVP: no mishap pools authored. Return None to skip.
    # When pools are created, this will query by deficit range.
    return None


def use_technique(
    *,
    character: ObjectDB,
    technique: Technique,
    resolve_fn: Callable[..., Any],
    confirm_overburn: bool = True,
    check_result: CheckResult | None = None,
) -> TechniqueUseResult:
    """Orchestrate technique use: cost -> checkpoint -> resolve -> mishap.

    Args:
        character: The character using the technique.
        technique: The technique being used.
        resolve_fn: Callable that performs the actual resolution
            (challenge, scene action, etc). Called with no args.
        confirm_overburn: Whether the player confirms overburn.
            In real usage, the pipeline pauses to ask. For the
            service layer, the caller passes the decision.
        check_result: If provided, reused for mishap consequence
            selection. If None, mishap pool selection still happens
            but consequence selection is skipped.

    Returns:
        TechniqueUseResult with cost info, resolution, and mishap.
    """
    # Step 1: Calculate runtime stats
    stats = get_runtime_technique_stats(technique, character)

    # Step 2: Calculate effective anima cost
    # Note: TOCTOU window between this read and deduct_anima's
    # select_for_update. Acceptable for MVP (low concurrency).
    # Future: move lock earlier if concurrent technique use matters.
    anima = CharacterAnima.objects.get(character=character)
    cost = calculate_effective_anima_cost(
        base_cost=technique.anima_cost,
        runtime_intensity=stats.intensity,
        runtime_control=stats.control,
        current_anima=anima.current,
    )

    # Step 3: Safety checkpoint
    severity = get_overburn_severity(cost.deficit) if cost.is_overburn else None

    if cost.is_overburn and not confirm_overburn:
        return TechniqueUseResult(
            anima_cost=cost,
            overburn_severity=severity,
            confirmed=False,
        )

    # Step 4: Deduct anima
    deduct_anima(character, cost.effective_cost)

    # Step 5 + 6: Resolution (capability value enhancement is the caller's
    # responsibility — they pass runtime_intensity to calculate_value)
    resolution_result = resolve_fn()

    # Step 7: Apply overburn condition (future — needs authored condition)
    # When Anima Warp condition template exists:
    # if deficit > 0: apply_condition(character, "anima_warp", severity=deficit)

    # Step 8: Mishap rider
    mishap = None
    control_deficit = stats.intensity - stats.control
    if control_deficit > 0:
        pool = select_mishap_pool(control_deficit)
        if pool is not None and check_result is not None:
            mishap = _resolve_mishap(character, pool, check_result)

    return TechniqueUseResult(
        anima_cost=cost,
        overburn_severity=severity,
        confirmed=True,
        resolution_result=resolution_result,
        mishap=mishap,
    )


def _resolve_mishap(
    character: ObjectDB,
    pool: ConsequencePool,
    check_result: CheckResult,
) -> MishapResult | None:
    """Resolve a mishap rider using the main check result."""
    from actions.services import get_effective_consequences  # noqa: PLC0415
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        select_consequence_from_result,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415

    consequences = get_effective_consequences(pool)
    if not consequences:
        return None

    pending = select_consequence_from_result(character, check_result, consequences)
    context = ResolutionContext(character=character)
    applied = apply_resolution(pending, context)

    return MishapResult(
        consequence_label=pending.selected_consequence.label,
        applied_effect_ids=[e.created_instance.pk for e in applied if e.created_instance],
    )
