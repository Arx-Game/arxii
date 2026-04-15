"""
Magic system service functions.

This module provides service functions for the magic system, including
calculations for aura percentages based on affinity and resonance totals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import (
    ALTERATION_TIER_CAPS,
    MIN_ALTERATION_DESCRIPTION_LENGTH,
)
from world.magic.models import (
    CharacterAnima,
    CharacterResonanceTotal,
    IntensityTier,
    MagicalAlterationTemplate,
    SoulfrayConfig,
)
from world.magic.types import (
    AffinityType,
    AnimaCostResult,
    AuraPercentages,
    MishapResult,
    PendingAlterationResult,
    RuntimeTechniqueStats,
    SoulfrayResult,
    SoulfrayWarning,
    TechniqueUseResult,
)
from world.mechanics.constants import (
    TECHNIQUE_STAT_CATEGORY_NAME,
    TECHNIQUE_STAT_CONTROL,
    TECHNIQUE_STAT_INTENSITY,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from django.db.models import QuerySet
    from evennia.objects.models import ObjectDB

    from actions.models.action_templates import ConsequencePool
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.magic.models import (
        Affinity,
        Resonance as ResonanceModel,
        Technique,
    )
    from world.mechanics.models import ModifierTarget
    from world.scenes.models import Scene


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


def _get_technique_stat_targets() -> dict[str, ModifierTarget]:
    """Look up technique_stat ModifierTargets in a single query.

    Returns a dict mapping target name to ModifierTarget instance.
    Missing keys mean no modifiers are configured for that stat.
    """
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    return {
        t.name: t
        for t in ModifierTarget.objects.filter(
            category__name=TECHNIQUE_STAT_CATEGORY_NAME,
            name__in=[TECHNIQUE_STAT_INTENSITY, TECHNIQUE_STAT_CONTROL],
        ).select_related("category")
    }


def _get_character_sheet(character: ObjectDB) -> CharacterSheet | None:
    """Get the CharacterSheet for a character, or None if not found."""
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    try:
        return CharacterSheet.objects.get(character=character)
    except CharacterSheet.DoesNotExist:
        return None


def _get_social_safety_bonus() -> int:
    """Return the social safety control bonus for unengaged characters.

    Hardcoded to 10 for now.
    TODO: Replace with authored data (e.g., a GlobalSetting or config model).
    """
    return 10


def _get_intensity_tier_control_modifier(runtime_intensity: int) -> int:
    """Look up the IntensityTier for a given intensity and return its control_modifier.

    Finds the highest tier whose threshold is <= runtime_intensity.
    Returns 0 if no tier matches.
    """
    tier = (
        IntensityTier.objects.filter(threshold__lte=runtime_intensity)
        .order_by("-threshold")
        .first()
    )
    if tier is None:
        return 0
    return tier.control_modifier


def get_runtime_technique_stats(
    technique: Technique,
    character: ObjectDB | None,
) -> RuntimeTechniqueStats:
    """Calculate runtime intensity and control for a technique.

    Combines base values with identity modifiers (from CharacterModifier),
    process modifiers (from CharacterEngagement), social safety bonus
    (when not engaged), and IntensityTier control modifier.
    """
    if character is None:
        return RuntimeTechniqueStats(
            intensity=technique.intensity,
            control=technique.control,
        )

    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    # Identity stream
    identity_intensity = 0
    identity_control = 0
    sheet = _get_character_sheet(character)
    if sheet is not None:
        stat_targets = _get_technique_stat_targets()
        if TECHNIQUE_STAT_INTENSITY in stat_targets:
            identity_intensity = get_modifier_total(sheet, stat_targets[TECHNIQUE_STAT_INTENSITY])
        if TECHNIQUE_STAT_CONTROL in stat_targets:
            identity_control = get_modifier_total(sheet, stat_targets[TECHNIQUE_STAT_CONTROL])

    # Process stream
    process_intensity = 0
    process_control = 0
    social_safety = 0
    try:
        engagement = CharacterEngagement.objects.get(character=character)
        process_intensity = engagement.intensity_modifier
        process_control = engagement.control_modifier
    except CharacterEngagement.DoesNotExist:
        social_safety = _get_social_safety_bonus()

    # Sum
    runtime_intensity = technique.intensity + identity_intensity + process_intensity
    runtime_control = technique.control + identity_control + process_control + social_safety

    # IntensityTier control modifier
    tier_control = _get_intensity_tier_control_modifier(runtime_intensity)
    runtime_control += tier_control

    return RuntimeTechniqueStats(
        intensity=runtime_intensity,
        control=runtime_control,
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


def calculate_soulfray_severity(
    current_anima: int,
    max_anima: int,
    deficit: int,
    config: SoulfrayConfig,
) -> int:
    """Compute Soulfray severity contribution from post-deduction anima state."""
    from decimal import Decimal  # noqa: PLC0415
    from math import ceil  # noqa: PLC0415

    if max_anima <= 0:
        return 0

    ratio = Decimal(current_anima) / Decimal(max_anima)
    threshold = config.soulfray_threshold_ratio

    if ratio >= threshold:
        return 0

    depletion = float((threshold - ratio) / threshold)
    severity = ceil(config.severity_scale * depletion)

    if deficit > 0:
        severity += ceil(config.deficit_scale * deficit)

    return severity


def get_soulfray_warning(character: ObjectDB) -> SoulfrayWarning | None:
    """Return the current Soulfray stage warning for the safety checkpoint."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415

    soulfray_instance = (
        ConditionInstance.objects.filter(
            target=character,
            condition__name=SOULFRAY_CONDITION_NAME,
        )
        .select_related("current_stage", "current_stage__consequence_pool")
        .first()
    )

    if soulfray_instance is None or soulfray_instance.current_stage is None:
        return None

    stage = soulfray_instance.current_stage
    has_death_risk = False
    if stage.consequence_pool_id:
        from world.checks.models import Consequence  # noqa: PLC0415

        has_death_risk = Consequence.objects.filter(
            pool_entries__pool=stage.consequence_pool,
            character_loss=True,
        ).exists()

    return SoulfrayWarning(
        stage_name=stage.name,
        stage_description=stage.description,
        has_death_risk=has_death_risk,
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


def select_mishap_pool(control_deficit: int) -> ConsequencePool | None:
    """Select a control mishap consequence pool based on deficit magnitude."""
    from django.db import models as db_models  # noqa: PLC0415

    from world.magic.models import MishapPoolTier  # noqa: PLC0415

    tier = (
        MishapPoolTier.objects.filter(min_deficit__lte=control_deficit)
        .filter(
            db_models.Q(max_deficit__gte=control_deficit) | db_models.Q(max_deficit__isnull=True),
        )
        .order_by("-min_deficit")
        .first()
    )
    return tier.consequence_pool if tier else None


def use_technique(
    *,
    character: ObjectDB,
    technique: Technique,
    resolve_fn: Callable[..., Any],
    confirm_soulfray_risk: bool = True,
    check_result: CheckResult | None = None,
) -> TechniqueUseResult:
    """Orchestrate technique use: cost -> checkpoint -> resolve -> soulfray -> mishap."""
    from world.magic.models import SoulfrayConfig  # noqa: PLC0415

    # Step 1: Calculate runtime stats
    stats = get_runtime_technique_stats(technique, character)

    # Step 2: Calculate effective anima cost
    anima = CharacterAnima.objects.get(character=character)
    cost = calculate_effective_anima_cost(
        base_cost=technique.anima_cost,
        runtime_intensity=stats.intensity,
        runtime_control=stats.control,
        current_anima=anima.current,
    )

    # Step 3: Safety checkpoint (Soulfray stage-driven)
    soulfray_warning = get_soulfray_warning(character)

    if soulfray_warning and not confirm_soulfray_risk:
        return TechniqueUseResult(
            anima_cost=cost,
            soulfray_warning=soulfray_warning,
            confirmed=False,
        )

    # Step 4: Deduct anima
    deficit = deduct_anima(character, cost.effective_cost)

    # Steps 5 + 6: Resolution
    resolution_result = resolve_fn()

    # Extract check_result from resolution if not provided explicitly
    effective_check_result = check_result
    if effective_check_result is None and hasattr(resolution_result, "main_result"):
        main = resolution_result.main_result
        if main is not None and hasattr(main, "check_result"):
            effective_check_result = main.check_result

    # Step 7: Soulfray accumulation and stage consequences
    soulfray_result = None
    soulfray_config = SoulfrayConfig.objects.first()
    if soulfray_config:
        anima.refresh_from_db()
        soulfray_severity = calculate_soulfray_severity(
            current_anima=anima.current,
            max_anima=anima.maximum,
            deficit=deficit,
            config=soulfray_config,
        )

        if soulfray_severity > 0:
            soulfray_result = _handle_soulfray_accumulation(
                character=character,
                soulfray_severity=soulfray_severity,
                soulfray_config=soulfray_config,
                technique_check_result=effective_check_result,
            )

    # Step 8: Mishap rider
    mishap = None
    control_deficit = stats.intensity - stats.control
    if control_deficit > 0:
        pool = select_mishap_pool(control_deficit)
        if pool is not None and effective_check_result is not None:
            mishap = _resolve_mishap(character, pool, effective_check_result)

    return TechniqueUseResult(
        anima_cost=cost,
        soulfray_warning=soulfray_warning,
        confirmed=True,
        resolution_result=resolution_result,
        soulfray_result=soulfray_result,
        mishap=mishap,
    )


def _handle_soulfray_accumulation(
    *,
    character: ObjectDB,
    soulfray_severity: int,
    soulfray_config: SoulfrayConfig,
    technique_check_result: CheckResult | None,
) -> SoulfrayResult:
    """Handle Soulfray severity accumulation, stage advancement, and consequence pool."""
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        select_consequence_from_result,
    )
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.conditions.models import (  # noqa: PLC0415
        ConditionCheckModifier,
        ConditionInstance,
        ConditionTemplate,
    )
    from world.conditions.services import (  # noqa: PLC0415
        advance_condition_severity,
        apply_condition,
    )
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415
    from world.magic.models import TechniqueOutcomeModifier  # noqa: PLC0415

    # Find or create Soulfray condition
    soulfray_instance = (
        ConditionInstance.objects.filter(
            target=character,
            condition__name=SOULFRAY_CONDITION_NAME,
        )
        .select_related("current_stage")
        .first()
    )

    if soulfray_instance is None:
        soulfray_template = ConditionTemplate.objects.get(
            name=SOULFRAY_CONDITION_NAME,
        )
        result = apply_condition(target=character, condition=soulfray_template)
        soulfray_instance = result.instance
        # apply_condition creates with severity=1. Use advance_condition_severity
        # to set the real severity and resolve the correct stage.
        advance_condition_severity(soulfray_instance, soulfray_severity - 1)
        soulfray_instance.refresh_from_db()

        return SoulfrayResult(
            severity_added=soulfray_severity,
            stage_name=(
                soulfray_instance.current_stage.name if soulfray_instance.current_stage else None
            ),
            stage_advanced=soulfray_instance.current_stage is not None,
        )

    # Advance existing condition
    advance_result = advance_condition_severity(soulfray_instance, soulfray_severity)
    soulfray_instance.refresh_from_db()

    # Fire stage consequence pool if present
    resilience_check = None
    stage_consequence = None
    current_stage = soulfray_instance.current_stage

    if current_stage and current_stage.consequence_pool_id:
        from actions.services import get_effective_consequences  # noqa: PLC0415

        consequences = get_effective_consequences(
            current_stage.consequence_pool,
        )
        if consequences:
            # 1. Stage penalty via ConditionCheckModifier
            stage_modifier = 0
            stage_check_mod = ConditionCheckModifier.objects.filter(
                stage=current_stage,
                check_type=soulfray_config.resilience_check_type,
            ).first()
            if stage_check_mod:
                stage_modifier = stage_check_mod.modifier_value

            # 2. Technique outcome modifier (botch = penalty, crit = bonus)
            outcome_modifier = 0
            if technique_check_result and technique_check_result.outcome:
                outcome_mod = TechniqueOutcomeModifier.objects.filter(
                    outcome=technique_check_result.outcome,
                ).first()
                if outcome_mod:
                    outcome_modifier = outcome_mod.modifier_value

            total_modifier = stage_modifier + outcome_modifier

            # Perform resilience check
            resilience_check = perform_check(
                character=character,
                check_type=soulfray_config.resilience_check_type,
                target_difficulty=soulfray_config.base_check_difficulty,
                extra_modifiers=total_modifier,
            )

            # Select and apply consequence
            pending = select_consequence_from_result(
                character,
                resilience_check,
                consequences,
            )
            context = ResolutionContext(character=character)
            applied = apply_resolution(pending, context)
            if applied:
                stage_consequence = applied[0]

    return SoulfrayResult(
        severity_added=soulfray_severity,
        stage_name=current_stage.name if current_stage else None,
        stage_advanced=advance_result.stage_changed,
        resilience_check=resilience_check,
        stage_consequence=stage_consequence,
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


def create_pending_alteration(  # noqa: PLR0913 — kw-only snapshot fields are intentional
    *,
    character: CharacterSheet,
    tier: int,
    origin_affinity: Affinity,
    origin_resonance: ResonanceModel,
    scene: Scene | None,
    triggering_technique: Technique | None = None,
    triggering_intensity: int | None = None,
    triggering_control: int | None = None,
    triggering_anima_cost: int | None = None,
    triggering_anima_deficit: int | None = None,
    triggering_soulfray_stage: int | None = None,
    audere_active: bool = False,
) -> PendingAlterationResult:
    """Create or escalate a PendingAlteration for a character.

    Same-scene dedup: if an OPEN pending exists for the same character +
    scene, upgrade its tier if the new tier is higher. Otherwise no-op.
    Different scenes (or scene=None) always create new pendings.
    """
    from world.magic.constants import PendingAlterationStatus  # noqa: PLC0415
    from world.magic.models import PendingAlteration  # noqa: PLC0415

    snapshot_fields = {
        "triggering_technique": triggering_technique,
        "triggering_intensity": triggering_intensity,
        "triggering_control": triggering_control,
        "triggering_anima_cost": triggering_anima_cost,
        "triggering_anima_deficit": triggering_anima_deficit,
        "triggering_soulfray_stage": triggering_soulfray_stage,
        "audere_active": audere_active,
    }

    if scene is not None:
        existing = PendingAlteration.objects.filter(
            character=character,
            triggering_scene=scene,
            status=PendingAlterationStatus.OPEN,
        ).first()

        if existing is not None:
            if tier > existing.tier:
                previous_tier = existing.tier
                existing.tier = tier
                for field_name, value in snapshot_fields.items():
                    setattr(existing, field_name, value)
                existing.save()
                return PendingAlterationResult(
                    pending=existing,
                    created=False,
                    previous_tier=previous_tier,
                )
            return PendingAlterationResult(
                pending=existing,
                created=False,
                previous_tier=None,
            )

    pending = PendingAlteration.objects.create(
        character=character,
        tier=tier,
        origin_affinity=origin_affinity,
        origin_resonance=origin_resonance,
        triggering_scene=scene,
        **snapshot_fields,
    )
    return PendingAlterationResult(
        pending=pending,
        created=True,
        previous_tier=None,
    )


def validate_alteration_resolution(  # noqa: PLR0912,PLR0913,C901 — sequential validation gates, kw-only args
    *,
    pending_tier: int,
    pending_affinity_id: int,
    pending_resonance_id: int,
    payload: dict,
    is_staff: bool,
    character_sheet: CharacterSheet | None = None,
) -> list[str]:
    """Validate a resolution payload against the pending's tier and origin.

    Returns a list of error strings. Empty list = valid.
    character_sheet is required for library duplicate checks.
    """
    errors: list[str] = []
    tier = payload.get("tier")
    caps = ALTERATION_TIER_CAPS.get(pending_tier, {})

    if tier != pending_tier:
        errors.append(f"Tier mismatch: payload tier {tier} != pending tier {pending_tier}.")

    if payload.get("origin_affinity_id") != pending_affinity_id:
        errors.append("Origin affinity does not match the pending alteration.")

    if payload.get("origin_resonance_id") != pending_resonance_id:
        errors.append("Origin resonance does not match the pending alteration.")

    weakness = payload.get("weakness_magnitude", 0)
    if weakness > caps.get("weakness_cap", 0):
        errors.append(
            f"Weakness magnitude {weakness} exceeds tier {pending_tier} cap "
            f"of {caps['weakness_cap']}."
        )
    if weakness > 0 and not payload.get("weakness_damage_type_id"):
        errors.append("weakness_damage_type is required when weakness_magnitude > 0.")

    resonance = payload.get("resonance_bonus_magnitude", 0)
    if resonance > caps.get("resonance_cap", 0):
        errors.append(
            f"Resonance bonus magnitude {resonance} exceeds tier {pending_tier} cap "
            f"of {caps['resonance_cap']}."
        )

    social = payload.get("social_reactivity_magnitude", 0)
    if social > caps.get("social_cap", 0):
        errors.append(
            f"Social reactivity magnitude {social} exceeds tier {pending_tier} cap "
            f"of {caps['social_cap']}."
        )

    if caps.get("visibility_required") and not payload.get("is_visible_at_rest"):
        errors.append(f"is_visible_at_rest must be True at tier {pending_tier}.")

    for field in ("player_description", "observer_description"):
        value = payload.get(field, "")
        if len(value) < MIN_ALTERATION_DESCRIPTION_LENGTH:
            errors.append(
                f"{field} must be at least {MIN_ALTERATION_DESCRIPTION_LENGTH} characters "
                f"(got {len(value)})."
            )

    if payload.get("is_library_entry") and not is_staff:
        errors.append("Only staff can create library entries.")

    # Library use-as-is duplicate check
    library_pk = payload.get("library_entry_pk")
    if library_pk and character_sheet is not None:
        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        library_entry = MagicalAlterationTemplate.objects.filter(
            pk=library_pk,
            is_library_entry=True,
        ).first()
        if library_entry is None:
            errors.append("Library entry not found or not a library entry.")
        elif ConditionInstance.objects.filter(
            target=character_sheet.character,
            condition=library_entry.condition_template,
        ).exists():
            errors.append("Character already has this condition active.")

    return errors
