"""Vitals service layer — survivability pipeline.

Handles damage consequences: knockout checks, death checks, and permanent
wound application. System-agnostic — callable by combat, missions, traps,
or any damage source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from world.checks.models import CheckCategory, CheckType
from world.checks.services import collect_check_modifiers, perform_check
from world.vitals.constants import (
    DEATH_CHECK_NAME,
    DEATH_HEALTH_THRESHOLD,
    DERIVED_STATUS_ALIVE,
    DERIVED_STATUS_DEAD,
    DERIVED_STATUS_DYING,
    DERIVED_STATUS_INCAPACITATED,
    ENDURANCE_CHECK_NAME,
    KNOCKOUT_HEALTH_THRESHOLD,
    PERMANENT_WOUND_THRESHOLD,
    SURVIVABILITY_CHECK_CATEGORY,
    CharacterLifeState,
)
from world.vitals.types import DamageConsequenceResult

if TYPE_CHECKING:
    from collections.abc import Iterator

    from actions.models.consequence_pools import ConsequencePool
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType as CheckTypeHint, Consequence, ConsequenceEffect
    from world.checks.types import PendingResolution
    from world.conditions.models import ConditionInstance, ConditionTemplate, DamageType
    from world.vitals.models import VitalsConsequenceConfig


def is_dead(character_sheet: CharacterSheet | None) -> bool:
    """Return True if the character's mortality marker is DEAD.

    Accepts the Optional sheet so callers can pass `character.sheet_data`
    directly without a None guard — a missing sheet (e.g., NPCs not yet set up
    with health tracking) is treated as not-dead.
    """
    if character_sheet is None:
        return False
    try:
        return character_sheet.vitals.life_state == CharacterLifeState.DEAD
    except (AttributeError, ObjectDoesNotExist):
        return False


def is_alive(character_sheet: CharacterSheet | None) -> bool:
    """Return True if the character is not dead.

    Convenience inverse of is_dead. A character with no vitals row is
    considered alive (same defensive assumption as is_dead returning False).
    """
    return not is_dead(character_sheet)


def can_act(character_sheet: CharacterSheet | None) -> bool:
    """Coarse 'can engage at all' gate: not dead AND has awareness.

    Per-technique requirements are checked separately by technique_performable;
    this is the cheap round-participation precondition. Degrades gracefully if
    the awareness capability is not seeded (returns True rather than blocking).

    A dying-but-conscious character keeps awareness → can_act True. An
    Unconscious character has awareness 0 → can_act False.
    """
    from world.conditions.constants import (  # noqa: PLC0415
        FoundationalCapability,
    )
    from world.conditions.models import (  # noqa: PLC0415
        CapabilityType,
    )
    from world.conditions.services import (  # noqa: PLC0415
        get_effective_capability_value,
    )

    if is_dead(character_sheet):
        return False
    if character_sheet is None:
        return True
    awareness = CapabilityType.objects.filter(name=FoundationalCapability.AWARENESS).first()
    if awareness is None:
        return True
    return get_effective_capability_value(character_sheet, awareness) > 0


def derive_character_status(character_sheet: CharacterSheet | None) -> str:
    """Derive a coarse, read-only life-status string for the wire/API.

    This replaces the removed persisted CharacterVitals.status field. It is
    computed at read time from the mortality marker, active conditions, and
    agency — there is no stored status. The richer frontend status surface is
    tracked by #521/#522.

    Precedence: dead > dying (active Bleeding-Out condition) > incapacitated
    (cannot act) > alive.
    """
    from world.conditions.constants import (  # noqa: PLC0415
        BLEED_OUT_CONDITION_NAME,
    )
    from world.conditions.models import (  # noqa: PLC0415
        ConditionInstance,
    )

    if is_dead(character_sheet):
        return DERIVED_STATUS_DEAD
    if character_sheet is None:
        return DERIVED_STATUS_ALIVE
    dying = ConditionInstance.objects.filter(
        target=character_sheet.character,
        condition__name=BLEED_OUT_CONDITION_NAME,
    ).exists()
    if dying:
        return DERIVED_STATUS_DYING
    if not can_act(character_sheet):
        return DERIVED_STATUS_INCAPACITATED
    return DERIVED_STATUS_ALIVE


def calculate_knockout_difficulty(*, health_pct: float) -> int:
    """Scale knockout check difficulty by how far below 20% health.

    Base difficulty and scaling are read from the VitalsConsequenceConfig singleton
    so they can be tuned without a code deploy.

    Returns 0 if above threshold (no check needed).
    """
    if health_pct > KNOCKOUT_HEALTH_THRESHOLD:
        return 0
    cfg = get_vitals_consequence_config()
    pct_below = int((KNOCKOUT_HEALTH_THRESHOLD - health_pct) * 100)
    return cfg.knockout_base_difficulty + (pct_below * cfg.knockout_scaling_per_percent)


def calculate_death_difficulty(*, health_pct: float) -> int:
    """Scale death check difficulty by depth of negative health.

    Base difficulty and scaling are read from the VitalsConsequenceConfig singleton
    so they can be tuned without a code deploy.

    Returns 0 if above zero (no check needed).
    """
    if health_pct > DEATH_HEALTH_THRESHOLD:
        return 0
    cfg = get_vitals_consequence_config()
    pct_below = int(abs(health_pct) * 100)
    return cfg.death_base_difficulty + (pct_below * cfg.death_scaling_per_percent)


def calculate_wound_difficulty(*, damage: int, max_health: int) -> int:
    """Scale wound check difficulty by how far damage exceeds 50% threshold.

    Base difficulty and scaling are read from the VitalsConsequenceConfig singleton
    so they can be tuned without a code deploy.

    Returns 0 if below threshold (no check needed).
    """
    if max_health <= 0:
        return 0
    damage_pct = damage / max_health
    if damage_pct < PERMANENT_WOUND_THRESHOLD:
        return 0
    cfg = get_vitals_consequence_config()
    pct_over = int((damage_pct - PERMANENT_WOUND_THRESHOLD) * 100)
    return cfg.wound_base_difficulty + (pct_over * cfg.wound_scaling_per_percent)


def _ensure_survival_category() -> CheckCategory:
    """Get or create the Survival CheckCategory, creating it if absent.

    Seeded on first use — no Trait fixtures required.
    """
    cat, _ = CheckCategory.objects.get_or_create(
        name=SURVIVABILITY_CHECK_CATEGORY,
        defaults={"description": "Survivability resistance checks", "display_order": 98},
    )
    return cat


def _ensure_endurance_check_type() -> CheckType:
    """Get or create the Endurance CheckType, creating it if absent.

    Used for both knockout and permanent wound resistance checks. Seeded on
    first use — trait-weightings are authored content and not seeded here.
    """
    check, _ = CheckType.objects.get_or_create(
        name=ENDURANCE_CHECK_NAME,
        defaults={
            "category": _ensure_survival_category(),
            "description": "Resist knockout and permanent wounds.",
        },
    )
    return check


def _ensure_death_check_type() -> CheckType:
    """Get or create the Mortal Resolve CheckType, creating it if absent.

    Used for death resistance when a character is brought below zero health.
    Seeded on first use — trait-weightings are authored content and not seeded here.
    """
    check, _ = CheckType.objects.get_or_create(
        name=DEATH_CHECK_NAME,
        defaults={
            "category": _ensure_survival_category(),
            "description": "Resist death when brought below zero health.",
        },
    )
    return check


def _wound_pool(damage_type: DamageType | None) -> ConsequencePool | None:
    """Resolve the wound pool for a damage type, falling back to the config default."""
    cfg = get_vitals_consequence_config()
    return (damage_type.wound_pool if damage_type else None) or cfg.default_wound_pool


def _death_pool(damage_type: DamageType | None) -> ConsequencePool | None:
    """Resolve the death pool for a damage type, falling back to the config default."""
    cfg = get_vitals_consequence_config()
    return (damage_type.death_pool if damage_type else None) or cfg.default_death_pool


def _knockout_pool() -> ConsequencePool | None:
    """Return the global knockout pool from the vitals consequence config."""
    return get_vitals_consequence_config().knockout_pool


def _unwrap_consequence(pending: PendingResolution) -> Consequence | None:
    """Unwrap WeightedConsequence; return None for unsaved fallback consequences."""
    from actions.types import WeightedConsequence  # noqa: PLC0415

    c = pending.selected_consequence
    if isinstance(c, WeightedConsequence):
        c = c.consequence
    return None if c.pk is None else c


def _apply_condition_effects(pending: PendingResolution) -> Iterator[ConsequenceEffect]:
    """Yield APPLY_CONDITION effects (with a condition_template) from the selected consequence."""
    from world.checks.constants import EffectType  # noqa: PLC0415

    c = _unwrap_consequence(pending)
    if c is None:
        return
    for effect in c.effects.all():
        if (
            effect.effect_type == EffectType.APPLY_CONDITION
            and effect.condition_template is not None
        ):
            yield effect


def _applied_condition_names(pending: PendingResolution) -> set[str]:
    """Return the names of every ConditionTemplate applied by the selected consequence.

    Inspects the selected consequence's APPLY_CONDITION ConsequenceEffects. Unwraps a
    WeightedConsequence to its underlying Consequence model (mirrors apply_resolution).
    Returns an empty set for unsaved (fallback) consequences.
    """
    return {e.condition_template.name for e in _apply_condition_effects(pending)}


def _applied_bleed_out(pending: PendingResolution) -> bool:
    """True if the selected consequence applied the Bleeding-Out condition."""
    from world.conditions.constants import (  # noqa: PLC0415
        BLEED_OUT_CONDITION_NAME,
    )

    return BLEED_OUT_CONDITION_NAME in _applied_condition_names(pending)


def _applied_unconscious(pending: PendingResolution) -> bool:
    """True if the selected consequence applied the Unconscious condition."""
    from world.conditions.constants import (  # noqa: PLC0415
        UNCONSCIOUS_CONDITION_NAME,
    )

    return UNCONSCIOUS_CONDITION_NAME in _applied_condition_names(pending)


def _wounds_from(pending: PendingResolution) -> list[ConditionTemplate]:
    """Return the ConditionTemplates applied by the selected wound consequence.

    A wound pool's consequences apply permanent-wound ConditionTemplates via
    APPLY_CONDITION effects — every applied template is a wound by construction.
    """
    return [e.condition_template for e in _apply_condition_effects(pending)]


def process_damage_consequences(
    character_sheet: CharacterSheet | None,
    damage_dealt: int,
    damage_type: DamageType | None,
    *,
    extra_modifiers: int = 0,
) -> DamageConsequenceResult:
    """Process survivability consequences after damage is applied.

    Checks thresholds in order: permanent wound, death, knockout. Each tier that
    fires resolves through a consequence pool (tiered, weighted, character-loss
    filtered) rather than a binary success/fail branch. Character stats,
    conditions, and modifiers always influence the outcome via the check.

    Death is condition-driven: the death pool applies Bleeding-Out (which
    advance_bleed_out drives toward death). The pool's character_loss row applies
    terminal-severity Bleeding-Out, which filter_character_loss swaps for a
    survivable tier when the character has positive rollmod.

    Pools degrade gracefully: a missing pool (unseeded DB) skips that tier so
    combat never crashes. Check types are self-seeded internally via
    _ensure_endurance_check_type and _ensure_death_check_type.

    Call AFTER writing the health change to CharacterVitals.

    Args:
        character_sheet: The damaged character's CharacterSheet (or None if
            the ObjectDB has no sheet — NPCs without vitals tracking).
        damage_dealt: How much damage was dealt this hit.
        damage_type: Type of damage (for wound/death pool routing).
        extra_modifiers: Additional modifiers (fatigue, conditions, etc.).
    """
    if character_sheet is None:
        return DamageConsequenceResult(message="No vitals found")
    try:
        vitals = character_sheet.vitals
    except (AttributeError, ObjectDoesNotExist):
        return DamageConsequenceResult(message="No vitals found")

    # Dead characters are exempt from further consequences.
    # Unconscious/dying characters (now conditions) CAN still take damage.
    if is_dead(character_sheet):
        return DamageConsequenceResult(message="Character is dead")

    result = DamageConsequenceResult()

    # Use clamped health_percentage for knockout (0-20% range).
    # For death, compute raw ratio so negative health increases difficulty.
    health_pct = vitals.health_percentage
    raw_health_pct = vitals.health / vitals.max_health if vitals.max_health > 0 else 0.0

    # 1. Permanent wound check
    wound_difficulty = calculate_wound_difficulty(
        damage=damage_dealt,
        max_health=vitals.max_health,
    )
    wound_pool = _wound_pool(damage_type)
    if wound_difficulty > 0 and wound_pool is not None:
        wound_check_type = _ensure_endurance_check_type()
        wound_breakdown = collect_check_modifiers(character_sheet, wound_check_type)
        pending = resolve_vitals_consequence(
            character_sheet,
            wound_check_type,
            wound_difficulty,
            wound_pool,
            extra_modifiers=extra_modifiers + wound_breakdown.total,
        )
        wounds = _wounds_from(pending)
        if wounds:
            result.wounds_applied.extend(wounds)
            result.modifier_breakdown = wound_breakdown

    # 2. Death check (health <= 0)
    death_difficulty = calculate_death_difficulty(health_pct=raw_health_pct)
    death_pool = _death_pool(damage_type)
    if death_difficulty > 0 and death_pool is not None:
        death_check_type = _ensure_death_check_type()
        death_breakdown = collect_check_modifiers(character_sheet, death_check_type)
        pending = resolve_vitals_consequence(
            character_sheet,
            death_check_type,
            death_difficulty,
            death_pool,
            extra_modifiers=extra_modifiers + death_breakdown.total,
        )
        result.modifier_breakdown = death_breakdown
        if _applied_bleed_out(pending):
            result.dying = True
            result.message = "took a lethal hit and is dying"
            return result

    # 3. Knockout check (health between 0% and 20%)
    knockout_difficulty = calculate_knockout_difficulty(
        health_pct=health_pct,
    )
    knockout_pool = _knockout_pool()
    if knockout_difficulty > 0 and knockout_pool is not None:
        ko_check_type = _ensure_endurance_check_type()
        ko_breakdown = collect_check_modifiers(character_sheet, ko_check_type)
        pending = resolve_vitals_consequence(
            character_sheet,
            ko_check_type,
            knockout_difficulty,
            knockout_pool,
            extra_modifiers=extra_modifiers + ko_breakdown.total,
        )
        result.modifier_breakdown = ko_breakdown
        if _applied_unconscious(pending):
            result.knocked_out = True
            result.message = "was knocked unconscious"
            return result

    return result


def _is_terminal_stage(instance: ConditionInstance) -> bool:
    """Return True when instance.current_stage is the last stage for its condition.

    A stage is terminal when no stage with a higher stage_order exists for the
    same ConditionTemplate.
    """
    from world.conditions.models import ConditionStage  # noqa: PLC0415

    if instance.current_stage is None:
        return False
    return not ConditionStage.objects.filter(
        condition=instance.condition,
        stage_order__gt=instance.current_stage.stage_order,
    ).exists()


def _mark_dead(character_sheet: CharacterSheet) -> None:
    """Stamp life_state=DEAD and died_at on the character's vitals row.

    No-op when the character has no vitals row (defensive; callers should
    gate on vitals existing before calling advance_bleed_out).
    """
    try:
        vitals = character_sheet.vitals
    except (AttributeError, ObjectDoesNotExist):
        return
    vitals.life_state = CharacterLifeState.DEAD
    vitals.died_at = timezone.now()
    vitals.save(update_fields=["life_state", "died_at"])


def advance_bleed_out(character_sheet: CharacterSheet | None) -> bool:
    """Advance staged bleed-out conditions toward death.

    For each active ConditionInstance whose condition.name == BLEED_OUT_CONDITION_NAME:
    - If current_stage is None or has no resist_check_type, skip.
    - Perform the resist check at the stage's resist_difficulty.
    - On failure (success_level < 0):
        - If this is the terminal stage (no higher stage_order exists), call
          _mark_dead(character_sheet) and return True.
        - Otherwise advance current_stage to the next higher stage_order and save.
    - On success / non-failure: hold (no change).

    Returns True if the character died during this call, else False.
    """
    from world.conditions.constants import (  # noqa: PLC0415
        BLEED_OUT_CONDITION_NAME,
    )
    from world.conditions.models import (  # noqa: PLC0415
        ConditionStage,
        ConditionTemplate,
    )
    from world.conditions.services import (  # noqa: PLC0415
        get_active_conditions,
    )

    if character_sheet is None:
        return False

    # perform_check still operates on ObjectDB; walk back at the boundary.
    # Refactoring that layer is queued for Phase 3 of the OBJECTDB_PARAM rollout.
    character = character_sheet.character

    # Route through get_active_conditions (honors suppression by default) rather
    # than filtering ConditionInstance directly — keeps bleed-out advancement
    # consistent with the rest of the conditions layer when bleed-out suppression
    # becomes an authored mechanic. Issue #601.
    try:
        bleed_out = ConditionTemplate.get_by_name(BLEED_OUT_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        return False
    instances = list(
        get_active_conditions(character, condition=bleed_out).select_related(
            "current_stage__resist_check_type"
        )
    )

    for instance in instances:
        stage = instance.current_stage
        if stage is None or stage.resist_check_type is None:
            continue

        result = perform_check(
            character,
            stage.resist_check_type,
            target_difficulty=stage.resist_difficulty,
        )

        if int(result.success_level) < 0:
            # Failed resist: advance or die
            if _is_terminal_stage(instance):
                _mark_dead(character_sheet)
                return True
            # Advance to the next stage
            next_stage = (
                ConditionStage.objects.filter(
                    condition=instance.condition,
                    stage_order__gt=stage.stage_order,
                )
                .order_by("stage_order")
                .first()
            )
            if next_stage is not None:
                instance.current_stage = next_stage
                instance.save(update_fields=["current_stage"])

    return False


def recompute_max_health(
    character_sheet: CharacterSheet,
    *,
    thread_addend: int = 0,
) -> int:
    """Derive max_health from base_max_health plus a thread-derived addend.

    Spec A §5.8 lines 1644–1657 names this the "canonical recomputation
    entry point". Phase 13 lands the minimal implementation: max_health =
    base_max_health + thread_addend, clamped to >= 0.

    Clamp-not-injure semantics (§3.8): if the new max drops below current
    health, current health is clamped down to the new max — the character
    never gets *injured* by a recomputation, only un-bolstered. If new max
    is >= current health, current is untouched (no free heal).

    No-op when the sheet has no CharacterVitals row: characters that haven't
    been set up with vitals (fresh test fixtures, non-combat NPCs) should
    not crash callers that are simply folding thread addends through.

    Args:
        character_sheet: CharacterSheet whose vitals to recompute.
        thread_addend: Sum of thread-derived MAX_HEALTH VITAL_BONUS
            contributions (passive tier-0 + active-pull tier-1+).

    Returns:
        The new max_health value, or 0 if the sheet has no vitals row.
    """
    try:
        vitals = character_sheet.vitals
    except ObjectDoesNotExist:
        return 0
    new_max = max(vitals.base_max_health + thread_addend, 0)
    update_fields: list[str] = []
    if vitals.max_health != new_max:
        vitals.max_health = new_max
        update_fields.append("max_health")
    if vitals.health > new_max:
        vitals.health = new_max
        update_fields.append("health")
    if update_fields:
        vitals.save(update_fields=update_fields)
    return new_max


def get_vitals_consequence_config() -> VitalsConsequenceConfig:
    """Return the VitalsConsequenceConfig singleton (pk=1), creating it lazily on first call.

    Holds the global knockout pool and the default wound/death pools used when a
    DamageType doesn't specify its own. Configure via the Django admin.
    """
    from world.vitals.models import VitalsConsequenceConfig  # noqa: PLC0415

    cfg, _ = VitalsConsequenceConfig.objects.get_or_create(pk=1)
    return cfg


def resolve_vitals_consequence(
    character_sheet: CharacterSheet,
    check_type: CheckTypeHint,
    target_difficulty: int,
    pool: ConsequencePool,
    *,
    extra_modifiers: int = 0,
) -> PendingResolution:
    """Resolve one survivability consequence through the consequence-pool pipeline.

    Performs the check, selects a tier-matched + character-loss-filtered Consequence
    from the pool, and applies its effects. Returns the PendingResolution.

    This is the seam Task 5 uses to route knockout/wound/death through pools.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        resolve_pool_consequences,
        select_consequence,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415

    # select_consequence + apply_resolution still operate on ObjectDB; walk
    # back at the boundary. Refactoring the checks layer is Phase 2 follow-up.
    character = character_sheet.character

    consequences = resolve_pool_consequences(pool)
    pending = select_consequence(
        character,
        check_type,
        target_difficulty,
        consequences,
        extra_modifiers=extra_modifiers,
    )
    apply_resolution(pending, ResolutionContext(character=character))
    return pending
