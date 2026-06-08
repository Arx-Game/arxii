"""Technique use / runtime stat service functions for the magic system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia_extensions.models import RoomProfile
from flows.constants import EventName
from flows.emit import emit_event
from flows.events.payloads import (
    TechniqueAffectedPayload,
    TechniqueCastPayload,
    TechniquePreCastPayload,
)
from world.magic.constants import AffinityInteractionKind, PowerStage
from world.magic.models import CharacterAnima, IntensityTier
from world.magic.services.anima import deduct_anima
from world.magic.services.resonance_environment import (
    evaluate_resonance_environment,
    resonance_environment_for_cast,
)
from world.magic.services.soulfray import (
    _handle_soulfray_accumulation,
    _resolve_mishap,
    calculate_soulfray_severity,
    get_soulfray_warning,
    select_mishap_pool,
)
from world.magic.types import (
    AnimaCostResult,
    ResonanceInvolvement,
    RuntimeTechniqueStats,
    TechniqueUseResult,
)
from world.magic.types.power_ledger import PowerLedger, PowerLedgerBuilder
from world.mechanics.constants import (
    TECHNIQUE_STAT_CATEGORY_NAME,
    TECHNIQUE_STAT_CONTROL,
    TECHNIQUE_STAT_INTENSITY,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any

    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.magic.models import SoulfrayConfig, Technique
    from world.magic.services.power_terms import ApplicableThread
    from world.magic.services.resonance_environment import ResonanceEnvironmentEffect
    from world.magic.types import MishapResult, SoulfrayResult
    from world.mechanics.models import ModifierTarget


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


def _get_power_targets() -> list[ModifierTarget]:
    """Look up all 'power'-category ModifierTargets in a single query.

    Returns all power targets (global, resonance-scoped, and damage-type-scoped).
    Caller filters by the technique's resonances and damage types.
    """
    from world.mechanics.constants import POWER_CATEGORY_NAME  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    return list(
        ModifierTarget.objects.filter(category__name=POWER_CATEGORY_NAME).select_related(
            "category", "target_resonance", "target_damage_type"
        )
    )


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


def _character_is_in_audere(character: ObjectDB) -> bool:
    """Return True if the character has an active Audere ConditionInstance."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.magic.audere import AUDERE_CONDITION_NAME  # noqa: PLC0415

    return ConditionInstance.objects.filter(
        target=character,
        condition__name=AUDERE_CONDITION_NAME,
    ).exists()


def _character_has_fatigue_collapse_immune(character: ObjectDB) -> bool:
    """Return True if the character has any active condition granting fatigue_collapse_immune."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return ConditionInstance.objects.filter(
        target=character,
        is_suppressed=False,
        resolved_at__isnull=True,
        condition__properties__name="fatigue_collapse_immune",
    ).exists()


def _build_resonance_involvements(
    *,
    technique: Technique,
    character: ObjectDB,
    runtime_intensity: int,
) -> tuple[ResonanceInvolvement, ...]:
    """Compute per-resonance involvement for one cast.

    stat_bonus_contribution splits runtime intensity equally across the
    technique's gift's resonances (the modifier system does not track
    per-resonance attribution; spec §10.1 acknowledges this as an
    impl-phase resolution).

    thread_pull_resonance_spent sums CombatPull.resonance_spent for the
    character's active pulls per resonance.
    """
    resonances = list(technique.gift.resonances.all())
    if not resonances:
        return ()

    per_resonance_share = runtime_intensity // len(resonances)
    pulls_by_resonance: dict[int, int] = {}
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        active_pulls = character.combat_pulls.active()
    except ObjectDoesNotExist:
        # Character has no CharacterSheet (e.g., NPCs); treat as no active pulls.
        active_pulls = []
    for pull in active_pulls:
        pulls_by_resonance[pull.resonance_id] = (
            pulls_by_resonance.get(pull.resonance_id, 0) + pull.resonance_spent
        )

    return tuple(
        ResonanceInvolvement(
            resonance=r,
            stat_bonus_contribution=per_resonance_share,
            thread_pull_resonance_spent=pulls_by_resonance.get(r.pk, 0),
        )
        for r in resonances
    )


def _power_term_label(provider: Callable[..., int]) -> str:
    """Human-readable ledger label for a power-term provider function.

    ``level_power_term`` → "level power"; falls back to the cleaned name for
    any provider that does not follow the ``*_term`` convention.
    """
    name = provider.__name__
    name = name.removesuffix("_term")
    return name.replace("_", " ")


def _partition_power_targets(
    *,
    technique: Technique | None,
) -> tuple[ModifierTarget | None, list[ModifierTarget]]:
    """Split scope-matched power targets into (multiplier_target, flat_targets).

    A target matches when it passes both scope gates (AND semantics; null = global):
    - Resonance: target_resonance is None, or matches a technique gift resonance.
    - Damage-type: target_damage_type is None, or matches a technique damage profile.
    Untyped damage profiles (damage_type=None) never count as a damage-type match.
    """
    from world.mechanics.constants import POWER_MULTIPLIER_TARGET_NAME  # noqa: PLC0415

    technique_resonance_ids: set[int] = set()
    technique_damage_type_ids: set[int] = set()
    if technique is not None:
        technique_resonance_ids = {r.id for r in technique.gift.resonances.all()}
        technique_damage_type_ids = {
            p.damage_type_id
            for p in technique.damage_profiles.all()
            if p.damage_type_id is not None
        }

    multiplier_target: ModifierTarget | None = None
    flat_targets: list[ModifierTarget] = []
    for target in _get_power_targets():
        resonance_matches = (
            target.target_resonance_id is None
            or target.target_resonance_id in technique_resonance_ids
        )
        damage_type_matches = (
            target.target_damage_type_id is None
            or target.target_damage_type_id in technique_damage_type_ids
        )
        if not (resonance_matches and damage_type_matches):
            continue
        if target.name == POWER_MULTIPLIER_TARGET_NAME:
            multiplier_target = target
        else:
            flat_targets.append(target)
    return multiplier_target, flat_targets


def _apply_power_multiplier_stage(
    builder: PowerLedgerBuilder,
    *,
    sheet: CharacterSheet,
    multiplier_target: ModifierTarget,
) -> None:
    """Add the aggregate MULTIPLIER entry (applies to base only) for ``multiplier_target``.

    The percent-delta and its source label are derived from identity + condition
    modifiers; immunity-blocked sources are excluded from the label.
    """
    from world.conditions.services import (  # noqa: PLC0415
        get_condition_modifier_breakdown,
        get_condition_modifier_total,
    )
    from world.mechanics.services import get_modifier_breakdown  # noqa: PLC0415

    mult_breakdown = get_modifier_breakdown(sheet, multiplier_target)
    mult_condition_rows = get_condition_modifier_breakdown(sheet, multiplier_target)
    delta = mult_breakdown.total + get_condition_modifier_total(sheet, multiplier_target)
    names = [
        s.source_name for s in mult_breakdown.sources if s.source_name and not s.blocked_by_immunity
    ]
    names += [name for name, _value in mult_condition_rows if name]
    label = ", ".join(names) if names else "power multipliers"
    builder.multiply(PowerStage.MULTIPLIER, label, delta)


def _environment_amplifies(environment: ResonanceEnvironmentEffect | None) -> bool:
    """True when the resonance environment adds power (ALIGNED AMPLIFY, positive magnitude).

    Only AMPLIFY adds power here. Double-count guards:
      - OPPOSED (REJECT/REPEL): NO power change — its penalty is the existing Step 10
        backfire; subtracting power here would double-count the same opposition.
      - ALIGNED persistent presence boon: applied as a ConditionInstance on move and
        already flows through the FLAT/condition stage; no entry here.
      - CORRUPT: deferred; no entry.
    """
    return (
        environment is not None
        and environment.kind == AffinityInteractionKind.AMPLIFY
        and environment.magnitude > 0
    )


def _derive_power(
    *,
    channeled_intensity: int,
    technique: Technique | None,
    character: ObjectDB | None,
    applicable_threads: Sequence[ApplicableThread] | None = None,
    environment: ResonanceEnvironmentEffect | None = None,
) -> PowerLedger:
    """Derive effective power as an ordered ledger. NEVER stored — recomputed each cast.

    The returned :class:`PowerLedger` records every contribution as an entry; its
    ``total`` is the effective power (floored at 0). The numerics are identical to
    the prior int-returning implementation::

        flat   = Σ (additive power contributions)
        delta  = Σ (power_multiplier percent-delta contributions)   # 0 when none
        scaled = round(channeled_intensity * (100 + delta) / 100)
        power  = max(0, scaled + flat + Σ provider(ctx))

    **Stage ordering vs. display ordering.** The multiplier mathematically applies
    to the BASE channeled intensity ONLY (never to flats or terms), so to reproduce
    the single-round ``round(base * (100 + delta) / 100)`` exactly we apply the
    MULTIPLIER stage FIRST (one aggregate call, never per-source — per-source
    ``multiply`` would round repeatedly and drift), then per-source FLAT adds, then
    TERM adds. The ledger therefore *displays* MULTIPLIER before FLAT; this is
    intentional and required for numeric fidelity.

    A target is matched when it passes both scope gates (AND semantics; null = global):
    - Resonance scope: target_resonance is None, or matches a technique gift resonance.
    - Damage-type scope: target_damage_type is None, or matches a technique damage profile.
    Untyped damage profiles (damage_type=None) never count as a damage-type match.
    Power-scoped contributions raise landed effect only; channeled intensity
    (anima/mishap/Soulfray) is untouched by construction.
    """
    from world.conditions.services import get_condition_modifier_breakdown  # noqa: PLC0415
    from world.magic.services.power_terms import (  # noqa: PLC0415
        PowerTermContext,
        get_power_term_providers,
    )
    from world.mechanics.services import get_modifier_breakdown  # noqa: PLC0415

    if character is None:
        return PowerLedgerBuilder(base=max(0, channeled_intensity)).build()
    sheet = _get_character_sheet(character)
    if sheet is None:
        return PowerLedgerBuilder(base=max(0, channeled_intensity)).build()

    multiplier_target, flat_targets = _partition_power_targets(technique=technique)

    builder = PowerLedgerBuilder(base=channeled_intensity, base_label="channeled intensity")

    # --- MULTIPLIER stage (applies to base only; single aggregate call) ---
    if multiplier_target is not None:
        _apply_power_multiplier_stage(
            builder,
            sheet=sheet,
            multiplier_target=multiplier_target,
        )

    # --- FLAT stage (per source; addition does not round) ---
    for target in flat_targets:
        for source in get_modifier_breakdown(sheet, target).sources:
            if source.blocked_by_immunity:
                continue
            builder.add(PowerStage.FLAT_MODIFIER, source.source_name, source.final_value)
        for name, value in get_condition_modifier_breakdown(sheet, target):
            builder.add(PowerStage.FLAT_MODIFIER, name, value)

    # --- TERM stage (per provider) ---
    ctx = PowerTermContext(
        sheet=sheet,
        technique=technique,
        applicable_threads=applicable_threads or [],
    )
    for provider in get_power_term_providers():
        builder.add(PowerStage.TERM, _power_term_label(provider), provider(ctx))

    # --- ENVIRONMENT stage (#639 Task 4): a place's cast-time resonance reaction ---
    if _environment_amplifies(environment):
        builder.add(PowerStage.ENVIRONMENT, "resonance environment", environment.magnitude)

    return builder.clamp_floor().build()


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
    strain_commitment: int = 0,
) -> AnimaCostResult:
    """Calculate effective anima cost using the delta formula.

    effective_cost = max(base_cost - (control - intensity), 0) + max(strain_commitment, 0)

    ``strain_commitment`` adds on top of the floored cost — the floor is the minimum
    before strain; strain then raises the effective cost (and potential deficit) above it.

    deficit = max(effective_cost - current_anima, 0)
    """
    control_delta = runtime_control - runtime_intensity
    effective_cost = max(base_cost - control_delta, 0) + max(strain_commitment, 0)
    deficit = max(effective_cost - current_anima, 0)

    return AnimaCostResult(
        base_cost=base_cost,
        effective_cost=effective_cost,
        control_delta=control_delta,
        current_anima=current_anima,
        deficit=deficit,
    )


def _evaluate_cast_environment(
    character: ObjectDB,
    caster_room: ObjectDB | None,
    technique: Technique,
) -> tuple[RoomProfile | None, ResonanceEnvironmentEffect | None]:
    """Resolve the caster's room profile and evaluate the resonance environment once.

    Returns ``(room_profile, environment_effect)``; both are ``None`` when the caster
    has no location or the location has no ``RoomProfile``.
    """
    if caster_room is None:
        return None, None
    try:
        room_profile = caster_room.room_profile
    except RoomProfile.DoesNotExist:
        return None, None
    environment_effect = evaluate_resonance_environment(
        caster=character, room=caster_room, technique=technique
    )
    return room_profile, environment_effect


def _reconcile_precast_ledger(pre_payload: TechniquePreCastPayload) -> PowerLedger:
    """Return the ledger reconciled against any pre-cast MODIFY_PAYLOAD power edit.

    Stage 6 (REACTIVE): when a hook edited ``payload.power``, the signed delta becomes a
    single REACTIVE entry so the ledger total matches the post-hook power. The ledger is
    the source of truth, so a hook driving power below 0 yields a floored (>=0) value.
    """
    effective_ledger = pre_payload.ledger
    if pre_payload.power == effective_ledger.total:
        return effective_ledger
    return (
        PowerLedgerBuilder.from_ledger(effective_ledger)
        .add(PowerStage.REACTIVE, "pre-cast edit", pre_payload.power - effective_ledger.total)
        .build()
    )


def _resolve_check_result(
    check_result: CheckResult | None,
    resolution_result: Any,
) -> CheckResult | None:
    """Return the explicit check_result, else pull it from the resolution result."""
    if check_result is not None:
        return check_result
    result = getattr(resolution_result, "check_result", None)  # noqa: GETATTR_LITERAL
    if result is not None:
        return result
    main = getattr(resolution_result, "main_result", None)  # noqa: GETATTR_LITERAL
    if main is not None:
        return getattr(main, "check_result", None)  # noqa: GETATTR_LITERAL
    return None


def _accumulate_soulfray(
    *,
    character: ObjectDB,
    anima: CharacterAnima,
    deficit: int,
    soulfray_config: SoulfrayConfig | None,
    check_result: CheckResult | None,
) -> SoulfrayResult | None:
    """Step 7: accumulate Soulfray severity and apply stage consequences.

    No-op (returns ``None``) when Soulfray is unconfigured or severity is non-positive.
    """
    if not soulfray_config:
        return None
    anima.refresh_from_db()
    soulfray_severity = calculate_soulfray_severity(
        current_anima=anima.current,
        max_anima=anima.maximum,
        deficit=deficit,
        config=soulfray_config,
    )
    if soulfray_severity <= 0:
        return None
    return _handle_soulfray_accumulation(
        character=character,
        soulfray_severity=soulfray_severity,
        soulfray_config=soulfray_config,
        technique_check_result=check_result,
    )


def _resolve_control_mishap(
    *,
    character: ObjectDB,
    stats: RuntimeTechniqueStats,
    check_result: CheckResult | None,
) -> MishapResult | None:
    """Step 8: resolve a control-deficit mishap rider, or ``None`` when none applies."""
    control_deficit = stats.intensity - stats.control
    if control_deficit <= 0:
        return None
    pool = select_mishap_pool(control_deficit)
    if pool is None or check_result is None:
        return None
    return _resolve_mishap(character, pool, check_result)


def _apply_technique_fatigue_step(
    *,
    sheet: CharacterSheet | None,
    character: ObjectDB,
    technique: Technique,
    cost: AnimaCostResult,
    strain_commitment: int,
) -> None:
    """Step 8b: accrue technique fatigue to the matching action-category pool.

    Collapse is suppressed when the character has the fatigue_collapse_immune condition.
    No-op for NPCs without a CharacterSheet or zero-cost casts.
    """
    if sheet is None or cost.effective_cost <= 0:
        return
    from world.fatigue.services import apply_technique_fatigue  # noqa: PLC0415

    apply_technique_fatigue(
        sheet,
        technique.action_category,
        cost.effective_cost,
        strain_commitment,
        immune_to_fatigue_collapse=_character_has_fatigue_collapse_immune(character),
    )


def _accrue_cast_corruption(
    *,
    sheet: CharacterSheet | None,
    technique_result: TechniqueUseResult,
) -> None:
    """Step 9: per-cast corruption accrual. NPCs without a CharacterSheet skip silently."""
    if sheet is None:
        return
    from world.magic.services.corruption import accrue_corruption_for_cast  # noqa: PLC0415

    technique_result.corruption_summary = accrue_corruption_for_cast(
        caster_sheet=sheet,
        technique_use_result=technique_result,
    )


def _react_resonance_environment(
    *,
    sheet: CharacterSheet | None,
    room_profile: RoomProfile | None,
    environment_effect: ResonanceEnvironmentEffect | None,
    technique: Technique,
    technique_result: TechniqueUseResult,
) -> None:
    """Step 10: universal resonance-environment reaction (backfire + defilement).

    Reuses the hoisted environment_effect / room_profile (#639/#722). The sheet guard
    keeps backfire/defile gated to magically-active casters; inert when room_profile or
    environment_effect is None. Runs no flows/events of its own.
    """
    if sheet is None or room_profile is None or environment_effect is None:
        return
    from world.magic.services.defilement import defile_place_for_cast  # noqa: PLC0415

    resonance_environment_for_cast(
        caster_sheet=sheet,
        room_profile=room_profile,
        technique=technique,
        effect=environment_effect,
    )
    # Defilement: a CASTER_DOMINANT caster overpowering an opposed place degrades it,
    # spreads its taint, and accrues caster->world corruption (issue #525). Inert unless
    # the gate is met.
    defile_place_for_cast(
        caster_sheet=sheet,
        room_profile=room_profile,
        technique=technique,
        technique_result=technique_result,
        effect=environment_effect,
    )


def _emit_cast_events(  # noqa: PLR0913 - frozen event payload fields
    *,
    character: ObjectDB,
    technique: Technique,
    caster_room: ObjectDB | None,
    effective_targets: list,
    intensity: int,
    effective_power: int,
    effective_ledger: PowerLedger,
    resolution_result: Any,
) -> None:
    """Emit the frozen TECHNIQUE_CAST event and a TECHNIQUE_AFFECTED event per target."""
    if caster_room is not None:
        emit_event(
            EventName.TECHNIQUE_CAST,
            TechniqueCastPayload(
                caster=character,
                technique=technique,
                targets=effective_targets,
                intensity=intensity,
                power=effective_power,
                ledger=effective_ledger,
                result=resolution_result,
            ),
            location=caster_room,
        )

    for affected_target in effective_targets:
        target_room = getattr(affected_target, "location", None)  # noqa: GETATTR_LITERAL
        if target_room is None:
            continue
        emit_event(
            EventName.TECHNIQUE_AFFECTED,
            TechniqueAffectedPayload(
                caster=character,
                technique=technique,
                target=affected_target,
                power=effective_power,
                ledger=effective_ledger,
                effect=resolution_result,
            ),
            location=target_room,
        )


def use_technique(  # noqa: PLR0913
    *,
    character: ObjectDB,
    technique: Technique,
    resolve_fn: Callable[..., Any],
    confirm_soulfray_risk: bool = True,
    check_result: CheckResult | None = None,
    targets: list | None = None,
    strain_commitment: int = 0,
) -> TechniqueUseResult:
    """Orchestrate technique use: cost -> checkpoint -> resolve -> soulfray -> mishap.

    ``strain_commitment`` is extra anima committed beyond the technique's normal
    effective cost (e.g. for Clash contributions). It defaults to ``0`` so every
    existing caller is unaffected. The strain adds on top of the floored
    effective cost via ``calculate_effective_anima_cost``.

    Emits reactive events:
    - TECHNIQUE_PRE_CAST (cancellable) — before anima deduction
    - TECHNIQUE_CAST (post-resolve, frozen)
    - TECHNIQUE_AFFECTED per target when *targets* is provided
    """
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
        strain_commitment=strain_commitment,
    )

    # Step 3: Safety checkpoint (Soulfray stage-driven)
    soulfray_warning = get_soulfray_warning(character)

    if soulfray_warning and not confirm_soulfray_risk:
        return TechniqueUseResult(
            anima_cost=cost,
            soulfray_warning=soulfray_warning,
            confirmed=False,
            technique=technique,
        )

    # --- TECHNIQUE_PRE_CAST (cancellable, before anima deduction) ---
    effective_targets = targets or []
    caster_room = getattr(character, "location", None)  # noqa: GETATTR_LITERAL

    # Evaluate the resonance-environment primitive ONCE per cast, before power
    # derivation. The result feeds the ENVIRONMENT power-shift stage here AND is
    # reused at Step 10 (backfire + defilement) — evaluate-once (#639/#722).
    room_profile, environment_effect = _evaluate_cast_environment(character, caster_room, technique)

    seed_ledger = _derive_power(
        channeled_intensity=stats.intensity,
        technique=technique,
        character=character,
        environment=environment_effect,
    )
    pre_payload = TechniquePreCastPayload(
        caster=character,
        technique=technique,
        targets=effective_targets,
        intensity=stats.intensity,
        power=seed_ledger.total,
        ledger=seed_ledger,
    )
    if caster_room is not None:
        stack = emit_event(
            EventName.TECHNIQUE_PRE_CAST,
            pre_payload,
            location=caster_room,
        )
        if stack.was_cancelled():
            return TechniqueUseResult(
                anima_cost=cost,
                confirmed=False,
                technique=technique,
            )

    # Read back power after any pre-cast MODIFY_PAYLOAD hooks (mutable payload) and
    # reconcile the ledger so its total matches; ledger is the source of truth.
    effective_ledger = _reconcile_precast_ledger(pre_payload)
    effective_power = effective_ledger.total

    # Step 4: Deduct anima
    deficit = deduct_anima(character, cost.effective_cost)

    # Steps 5 + 6: Resolution
    resolution_result = resolve_fn(power=effective_power, ledger=effective_ledger)

    # Extract check_result from resolution if not provided explicitly
    effective_check_result = _resolve_check_result(check_result, resolution_result)

    # Step 7: Soulfray accumulation and stage consequences
    soulfray_result = _accumulate_soulfray(
        character=character,
        anima=anima,
        deficit=deficit,
        soulfray_config=SoulfrayConfig.objects.first(),
        check_result=effective_check_result,
    )

    # Step 8: Mishap rider
    mishap = _resolve_control_mishap(
        character=character,
        stats=stats,
        check_result=effective_check_result,
    )

    # Step 8b: Technique fatigue — accrues to the matching action-category pool.
    # sheet is also used in Steps 9 and 10; NPCs without a CharacterSheet skip those paths.
    sheet = _get_character_sheet(character)
    _apply_technique_fatigue_step(
        sheet=sheet,
        character=character,
        technique=technique,
        cost=cost,
        strain_commitment=strain_commitment,
    )

    resonance_involvements = _build_resonance_involvements(
        technique=technique,
        character=character,
        runtime_intensity=stats.intensity,
    )

    technique_result = TechniqueUseResult(
        anima_cost=cost,
        soulfray_warning=soulfray_warning,
        confirmed=True,
        resolution_result=resolution_result,
        soulfray_result=soulfray_result,
        mishap=mishap,
        technique=technique,
        was_deficit=cost.deficit > 0,
        was_mishap=mishap is not None,
        was_audere=_character_is_in_audere(character),
        resonance_involvements=resonance_involvements,
    )

    # Step 9: Per-cast corruption accrual (Magic Scope #7)
    _accrue_cast_corruption(sheet=sheet, technique_result=technique_result)

    # Step 10: Universal resonance-environment reaction (core magic-physics; no flow/trigger)
    _react_resonance_environment(
        sheet=sheet,
        room_profile=room_profile,
        environment_effect=environment_effect,
        technique=technique,
        technique_result=technique_result,
    )

    # --- TECHNIQUE_CAST + TECHNIQUE_AFFECTED events (post-resolve, frozen) ---
    _emit_cast_events(
        character=character,
        technique=technique,
        caster_room=caster_room,
        effective_targets=effective_targets,
        intensity=stats.intensity,
        effective_power=effective_power,
        effective_ledger=effective_ledger,
        resolution_result=resolution_result,
    )

    return technique_result
