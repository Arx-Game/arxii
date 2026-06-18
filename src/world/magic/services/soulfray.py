"""Soulfray accumulation, severity, warning, and mishap service functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.models import SoulfrayConfig
from world.magic.types import MishapResult, SoulfrayResult, SoulfrayWarning

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.action_templates import ConsequencePool
    from world.checks.types import CheckResult
    from world.conditions.models import ConditionStage
    from world.mechanics.types import AppliedEffect


def nonlethal_severity_ceiling() -> int | None:
    """Highest Soulfray severity that does NOT reach a death-risk stage.

    A death-risk stage is one whose ``consequence_pool`` carries a
    ``character_loss`` consequence. The ceiling is ``(lowest such threshold) - 1``
    so a non-lethal cast can never accumulate enough severity to land on (or past)
    a stage that can kill. Returns ``None`` when no death-risk stage exists, meaning
    severity needs no bound.
    """
    from world.checks.models import Consequence  # noqa: PLC0415
    from world.conditions.models import ConditionStage  # noqa: PLC0415
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415

    death_pool_ids = set(
        Consequence.objects.filter(
            character_loss=True,
            pool_entries__pool__condition_stages__condition__name=SOULFRAY_CONDITION_NAME,
        ).values_list("pool_entries__pool_id", flat=True)
    )
    if not death_pool_ids:
        return None

    lowest = (
        ConditionStage.objects.filter(
            condition__name=SOULFRAY_CONDITION_NAME,
            consequence_pool_id__in=death_pool_ids,
            severity_threshold__isnull=False,
        )
        .order_by("severity_threshold")
        .values_list("severity_threshold", flat=True)
        .first()
    )
    if lowest is None:
        return None
    return max(lowest - 1, 0)


def _nonlethal_bounded_advance(
    severity_to_add: int,
    soulfray_instance: object | None,
) -> tuple[int, SoulfrayResult | None]:
    """Bound a non-lethal severity advance below the death-risk ceiling.

    Returns ``(bounded_severity, short_circuit)``. ``short_circuit`` is a
    no-severity-added :class:`SoulfrayResult` when the caster is already at/above the
    safe ceiling (the cast must add nothing); otherwise it is ``None`` and the caller
    proceeds with ``bounded_severity``. When no death-risk stage exists the advance is
    returned unchanged.
    """
    ceiling = nonlethal_severity_ceiling()
    if ceiling is None:
        return severity_to_add, None
    existing = soulfray_instance.severity if soulfray_instance is not None else 0
    bounded = min(severity_to_add, max(ceiling - existing, 0))
    if bounded > 0:
        return bounded, None
    # Already at/above the safe ceiling — preserve the current stage name, add nothing.
    stage_name = None
    if soulfray_instance is not None and soulfray_instance.current_stage:
        stage_name = soulfray_instance.current_stage.name
    return 0, SoulfrayResult(severity_added=0, stage_name=stage_name, stage_advanced=False)


def calculate_soulfray_severity(
    current_anima: int,
    max_anima: int,
    deficit: int,
    config: SoulfrayConfig,
    *,
    lethal: bool = True,
) -> int:
    """Compute Soulfray severity contribution from post-deduction anima state.

    ``lethal`` defaults to ``True`` so existing callers are unaffected. In a
    NON-LETHAL encounter (``lethal=False``) the returned severity is bounded below
    the first death-risk Soulfray stage (see ``nonlethal_severity_ceiling``), so a
    cast can never accumulate into stages that can kill.
    """
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

    if not lethal:
        ceiling = nonlethal_severity_ceiling()
        if ceiling is not None:
            severity = min(severity, ceiling)

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


def _handle_soulfray_accumulation(
    *,
    character: ObjectDB,
    soulfray_severity: int,
    soulfray_config: SoulfrayConfig,
    technique_check_result: CheckResult | None,
    lethal: bool = True,
) -> SoulfrayResult:
    """Handle Soulfray severity accumulation, stage advancement, and consequence pool."""
    from world.conditions.models import (  # noqa: PLC0415
        ConditionInstance,
        ConditionTemplate,
    )
    from world.conditions.services import (  # noqa: PLC0415
        advance_condition_severity,
        apply_condition,
    )
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415

    # Find or create Soulfray condition
    soulfray_instance = (
        ConditionInstance.objects.filter(
            target=character,
            condition__name=SOULFRAY_CONDITION_NAME,
        )
        .select_related("current_stage")
        .first()
    )

    # Non-lethal: bound the CUMULATIVE severity below the first death-risk stage so a
    # non-lethal cast can never advance into (or past) a stage that can kill. The
    # per-cast severity clamp alone is insufficient because advancement accumulates.
    if not lethal:
        soulfray_severity, short_circuit = _nonlethal_bounded_advance(
            soulfray_severity, soulfray_instance
        )
        if short_circuit is not None:
            return short_circuit

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

        # On first creation the pool is not fired; callers must trigger a second
        # accumulation for the stage threshold to evaluate.
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
    current_stage = soulfray_instance.current_stage
    resilience_check, stage_consequence = _fire_stage_consequence_pool(
        character=character,
        current_stage=current_stage,
        soulfray_config=soulfray_config,
        technique_check_result=technique_check_result,
        lethal=lethal,
    )

    return SoulfrayResult(
        severity_added=soulfray_severity,
        stage_name=current_stage.name if current_stage else None,
        stage_advanced=advance_result.stage_changed,
        resilience_check=resilience_check,
        stage_consequence=stage_consequence,
    )


def _fire_stage_consequence_pool(
    *,
    character: ObjectDB,
    current_stage: ConditionStage | None,
    soulfray_config: SoulfrayConfig,
    technique_check_result: CheckResult | None,
    lethal: bool,
) -> tuple[CheckResult | None, AppliedEffect | None]:
    """Fire a Soulfray stage's consequence pool, returning ``(resilience_check, applied)``.

    When ``lethal`` is False, ``character_loss`` consequences are filtered out of the
    pool before selection, so a non-lethal cast can never roll a death consequence.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        select_consequence_from_result,
    )
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.conditions.models import ConditionCheckModifier  # noqa: PLC0415
    from world.magic.models import TechniqueOutcomeModifier  # noqa: PLC0415

    if not current_stage or not current_stage.consequence_pool_id:
        return None, None

    from actions.services import get_effective_consequences  # noqa: PLC0415

    consequences = get_effective_consequences(current_stage.consequence_pool)
    if not lethal:
        # Non-lethal: a cast can never roll a character_loss consequence.
        consequences = [wc for wc in consequences if not wc.character_loss]
    if not consequences:
        return None, None

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

    # Perform resilience check
    resilience_check = perform_check(
        character=character,
        check_type=soulfray_config.resilience_check_type,
        target_difficulty=soulfray_config.base_check_difficulty,
        extra_modifiers=stage_modifier + outcome_modifier,
    )

    # Select and apply consequence
    pending = select_consequence_from_result(character, resilience_check, consequences)
    applied = apply_resolution(pending, ResolutionContext(character=character))
    return resilience_check, (applied[0] if applied else None)


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
