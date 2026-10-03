"""Soulfray accumulation, severity, warning, and mishap service functions."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.models import SoulfrayConfig
from world.magic.types import (
    MishapResult,
    SoulfrayResult,
    SoulfrayReveal,
    SoulfrayStageSummary,
    SoulfrayWarning,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.db.models import QuerySet
    from evennia.objects.models import ObjectDB

    from actions.models.action_templates import ConsequencePool
    from actions.models.consequence_pools import ConsequencePoolEntry
    from actions.types import WeightedConsequence
    from world.checks.types import CheckResult
    from world.conditions.models import ConditionStage
    from world.magic.models import CharacterAnima
    from world.mechanics.types import AppliedEffect


def nonlethal_ceiling_for(summaries: Sequence[SoulfrayStageSummary]) -> int | None:
    """Highest severity a non-lethal cast may reach, over an already-built ladder summary.

    ``(lowest severity_threshold among stages that can kill) - 1``, floored at 0;
    ``None`` when no stage with a threshold can kill. A time-based stage (no
    threshold) never sets the cap. Pure, so the Soulfray Stage Builder's Danger
    rail shows exactly the cap the game applies (#4089).
    """
    thresholds = [
        summary.stage.severity_threshold
        for summary in summaries
        if summary.can_kill and summary.stage.severity_threshold is not None
    ]
    if not thresholds:
        return None
    return max(min(thresholds) - 1, 0)


def nonlethal_severity_ceiling() -> int | None:
    """Highest Soulfray severity that does NOT reach a death-risk stage.

    A death-risk stage is one whose pool's EFFECTIVE consequences (parent rows
    merged, exclusions honoured, the same rule the draw uses) include a
    ``character_loss`` row. Before #4089 this read the stage pool's own entries
    only, so a lethal row inherited from a shared parent pool was drawn but
    never capped. Returns ``None`` when no death-risk stage exists.
    """
    return nonlethal_ceiling_for(soulfray_ladder_summary())


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
        from actions.services import get_effective_consequences  # noqa: PLC0415

        has_death_risk = any(
            wc.character_loss for wc in get_effective_consequences(stage.consequence_pool)
        )

    return SoulfrayWarning(
        stage_name=stage.name,
        stage_description=stage.description,
        has_death_risk=has_death_risk,
    )


def soulfray_stages() -> QuerySet[ConditionStage]:
    """Every stage of the Soulfray template, in ladder order.

    Exact name match, the same lookup every Soulfray consumer in this module uses.
    """
    from world.conditions.models import ConditionStage  # noqa: PLC0415
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415

    return ConditionStage.objects.filter(condition__name=SOULFRAY_CONDITION_NAME).order_by(
        "stage_order"
    )


def is_soulfray_stage(stage: ConditionStage) -> bool:
    """Whether ``stage`` belongs to the Soulfray template."""
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415

    return stage.condition.name == SOULFRAY_CONDITION_NAME


def soulfray_ladder_summary() -> list[SoulfrayStageSummary]:
    """Each Soulfray stage with its effective consequences, in ladder order (#4089).

    Two queries whatever the ladder size: the stages with their pools, then
    every entry of those pools and their parents. Never reads
    ``ConsequencePool.cached_consequences``, which is a cached_property on an
    identity-mapped row and outlives the request.
    """
    from actions.models import ConsequencePoolEntry  # noqa: PLC0415
    from actions.services import merge_pool_entries  # noqa: PLC0415

    stages = list(soulfray_stages().select_related("condition", "consequence_pool"))
    pool_ids: set[int] = set()
    for stage in stages:
        if stage.consequence_pool_id is not None:
            pool_ids.add(stage.consequence_pool_id)
            if stage.consequence_pool.parent_id is not None:
                pool_ids.add(stage.consequence_pool.parent_id)
    entries_by_pool: dict[int, list[ConsequencePoolEntry]] = defaultdict(list)
    if pool_ids:
        for entry in ConsequencePoolEntry.objects.filter(pool_id__in=pool_ids).select_related(
            "consequence"
        ):
            entries_by_pool[entry.pool_id].append(entry)

    summaries: list[SoulfrayStageSummary] = []
    for stage in stages:
        pool = stage.consequence_pool
        if pool is None:
            summaries.append(
                SoulfrayStageSummary(
                    stage=stage, pool=None, consequences=(), shared_consequence_ids=frozenset()
                )
            )
            continue
        parent_entries = entries_by_pool[pool.parent_id] if pool.parent_id else None
        consequences = tuple(merge_pool_entries(entries_by_pool[pool.pk], parent_entries))
        parent_ids = {e.consequence_id for e in parent_entries or () if not e.is_excluded}
        shared = frozenset(wc.consequence.pk for wc in consequences) & parent_ids
        summaries.append(
            SoulfrayStageSummary(
                stage=stage, pool=pool, consequences=consequences, shared_consequence_ids=shared
            )
        )
    return summaries


def select_mishap_pool(control_deficit: int) -> ConsequencePool | None:
    """Select a control mishap consequence pool based on deficit magnitude.

    Scans the cached catalog (#1846) in Python instead of a filtered
    ORDER BY ... LIMIT 1 query per call.
    """
    from world.magic.models import MishapPoolTier  # noqa: PLC0415

    candidates = [
        t
        for t in MishapPoolTier.objects.cached_all()
        if t.min_deficit <= control_deficit
        and (t.max_deficit is None or t.max_deficit >= control_deficit)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda t: t.min_deficit).consequence_pool


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
    resilience_check, stage_consequence, reveal = _fire_stage_consequence_pool(
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
        reveal=reveal,
    )


def accumulate_soulfray(  # noqa: PLR0913
    *,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    anima: CharacterAnima,
    deficit: int,
    soulfray_config: SoulfrayConfig | None,
    check_result: CheckResult | None,
    lethal: bool = True,
    defer_reveal: bool = False,
) -> SoulfrayResult | None:
    """Accumulate Soulfray severity from the pool state and apply stage consequences.

    Shared by ``use_technique`` (step 7) and, since #3573, by consented reactive
    protections (technique-interpose fire, standing-ward fire, upkeep). No-op when
    Soulfray is unconfigured or severity is non-positive. ``lethal=False`` bounds the
    accrued severity below the first death-risk stage.

    A dramatic stage draw's outcome wheel (``result.reveal``, #4089) is sent to the
    roller on commit. ``defer_reveal=True`` skips that send: the caller plays the
    reveal itself, in order with its own wheels, and must never drop it.
    """
    if not soulfray_config:
        return None
    anima.refresh_from_db()
    soulfray_severity = calculate_soulfray_severity(
        current_anima=anima.current,
        max_anima=anima.maximum,
        deficit=deficit,
        config=soulfray_config,
        lethal=lethal,
    )
    if soulfray_severity <= 0:
        return None
    result = _handle_soulfray_accumulation(
        character=character,
        soulfray_severity=soulfray_severity,
        soulfray_config=soulfray_config,
        technique_check_result=check_result,
        lethal=lethal,
    )
    if result.reveal is not None and not defer_reveal:
        reveal = result.reveal
        # On commit, as the scene path does: a rolled-back cast never spins a wheel.
        transaction.on_commit(lambda: deliver_soulfray_reveal(character, reveal))
    return result


def _fire_stage_consequence_pool(
    *,
    character: ObjectDB,
    current_stage: ConditionStage | None,
    soulfray_config: SoulfrayConfig,
    technique_check_result: CheckResult | None,
    lethal: bool,
) -> tuple[CheckResult | None, AppliedEffect | None, SoulfrayReveal | None]:
    """Fire a Soulfray stage's consequence pool: ``(resilience_check, applied, reveal)``.

    When ``lethal`` is False, ``character_loss`` consequences are filtered out of the
    pool before selection, so a non-lethal cast can never roll a death consequence.
    ``reveal`` is the draw's outcome wheel (#4089), built from the UNFILTERED tier,
    or ``None`` when the drawn tier is routine or nothing was drawn.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        select_consequence_from_result,
    )
    from world.checks.constants import ModifierSourceKind  # noqa: PLC0415
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.checks.types import ModifierContribution, ResolutionContext  # noqa: PLC0415
    from world.conditions.models import ConditionCheckModifier  # noqa: PLC0415
    from world.magic.models import TechniqueOutcomeModifier  # noqa: PLC0415

    if not current_stage or not current_stage.consequence_pool_id:
        return None, None, None

    from actions.services import get_effective_consequences  # noqa: PLC0415

    all_consequences = get_effective_consequences(current_stage.consequence_pool)
    consequences = all_consequences
    if not lethal:
        # Non-lethal: a cast can never roll a character_loss consequence. The wheel
        # still shows those rows (built from all_consequences below) and spins past
        # them: a player never learns a modifier removed an option (#4089 ruling).
        consequences = [wc for wc in all_consequences if not wc.character_loss]
    if not consequences:
        return None, None, None

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

    # Perform resilience check — route through the aggregator so condition,
    # rollmod, equipment, character, and capability modifiers reach this check
    # (#2758). The stage/outcome modifiers are domain-specific to soulfray and
    # pass as labeled SOULFRAY-kind contributions.
    soulfray_contributions = []
    if stage_modifier != 0:
        soulfray_contributions.append(
            ModifierContribution(
                source_kind=ModifierSourceKind.SOULFRAY,
                source_label="Soulfray stage penalty",
                value=stage_modifier,
            )
        )
    if outcome_modifier != 0:
        soulfray_contributions.append(
            ModifierContribution(
                source_kind=ModifierSourceKind.SOULFRAY,
                source_label="Technique outcome modifier",
                value=outcome_modifier,
            )
        )
    resilience_check = perform_check_with_modifiers(
        character=character,
        check_type=soulfray_config.resilience_check_type,
        target_difficulty=soulfray_config.base_check_difficulty,
        extra_contributions=soulfray_contributions or None,
    )

    # Select and apply consequence
    pending = select_consequence_from_result(character, resilience_check, consequences)
    applied = apply_resolution(pending, ResolutionContext(character=character))
    if lethal and pending.selected_consequence.character_loss:
        _resolve_soulfray_character_loss(character)
    reveal = _soulfray_reveal(
        stage=current_stage,
        soulfray_config=soulfray_config,
        check_result=resilience_check,
        consequences=all_consequences,
        selected_consequence_id=pending.selected_consequence.pk,
    )
    return resilience_check, (applied[0] if applied else None), reveal


def _soulfray_reveal(
    *,
    stage: ConditionStage,
    soulfray_config: SoulfrayConfig,
    check_result: CheckResult,
    consequences: list[WeightedConsequence],
    selected_consequence_id: int | None,
) -> SoulfrayReveal | None:
    """The #924 wheel for this draw, or None when the drawn tier carries no drama.

    Faces come from the UNFILTERED tier (``consequences`` is the full effective
    pool), so an option a modifier removed still shows; the landed face is the one
    the filtered draw picked, matched by pk (an unsaved fallback has none, so an
    empty draw sends no wheel). ``should_emit_theater`` is the existing #924 rule:
    the tier holds a ticked or a Can kill row.
    """
    from world.checks.theater import consequence_pool_faces, should_emit_theater  # noqa: PLC0415

    if selected_consequence_id is None:
        return None
    faces, selected = consequence_pool_faces(
        consequences=consequences,
        outcome=check_result.outcome,
        selected_consequence_id=selected_consequence_id,
        min_faces=1,
    )
    if selected is None or not should_emit_theater(faces):
        return None
    return SoulfrayReveal(
        title=soulfray_config.resilience_check_type.name,
        stage_label=f"Soulfray · {stage.name}",
        faces=tuple(faces),
        selected=selected,
    )


def deliver_soulfray_reveal(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - the roller, any puppet, as #924 theater
    reveal: SoulfrayReveal,
) -> bool:
    """Send one Soulfray reveal to the roller through the existing #924 emitter.

    Web-only by construction: telnet has no ``roulette_result`` output, and the
    outcome itself was already applied identically for both clients.
    """
    from world.checks.theater import maybe_emit_resolution_theater  # noqa: PLC0415

    return maybe_emit_resolution_theater(
        character=character,
        title=reveal.title,
        consequences=list(reveal.faces),
        selected=reveal.selected,
        stage_label=reveal.stage_label,
    )


def _resolve_soulfray_character_loss(character: ObjectDB) -> None:  # noqa: OBJECTDB_PARAM
    """A selected character_loss consequence is a certain death (#4098 d.9).

    Soulfray is now genuinely life-threatening (controller ruling, 2026-10-01):
    characters don't respawn. Routes through the vitals death seam, which defers
    under an active Audere/Audere Majora ``death_deferred`` condition and applies
    now otherwise. No NPC Audere (decision 10): a character with no CharacterSheet
    is skipped via the cached accessor, never re-queried.
    """
    from world.vitals import services as vitals_services  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None:
        return
    vitals_services.defer_or_apply_certain_death(sheet)


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
