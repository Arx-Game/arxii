"""Vitals service layer — survivability pipeline.

Handles damage consequences: knockout checks, death checks, and permanent
wound application. System-agnostic — callable by combat, missions, traps,
or any damage source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

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
    from collections.abc import Callable, Iterable, Iterator

    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType as CheckTypeHint, Consequence, ConsequenceEffect
    from world.checks.types import ModifierBreakdown, PendingResolution
    from world.conditions.models import (
        ConditionInstance,
        ConditionStage,
        ConditionTemplate,
        DamageType,
    )
    from world.conditions.types import RoundTickResult
    from world.scenes.models import Interaction
    from world.vitals.models import VitalsConsequenceConfig

ROUND_TICK_START = "start"
ROUND_TICK_END = "end"


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


def _record_combat_outcome(  # noqa: PLR0913 - mirrors record_consequence_outcome's context fields
    character_sheet: CharacterSheet,
    check_type: CheckTypeHint,
    pool: ConsequencePool,
    pending: PendingResolution,
    breakdown: ModifierBreakdown,
    combat_interaction_factory: Callable[[], Interaction] | None,
    summary: str,
) -> None:
    """Persist one survivability tier's resolution as a ConsequenceOutcome.

    No-op when ``combat_interaction_factory`` is None (e.g. the mechanics
    effect_handlers path) — the exactly-one-source constraint forbids a
    sourceless record. Otherwise the factory is invoked here to obtain the
    Interaction; because this function is only called from a firing tier, the
    Interaction is minted only when a consequence actually records (#864).

    Side-effect only (the existing return values are untouched). The selected
    Consequence is unwrapped from the pending resolution; an unsaved fallback
    consequence persists as a null selected_consequence (the outcome still
    records the pool + modifier provenance).
    """
    if combat_interaction_factory is None:
        return
    combat_interaction = combat_interaction_factory()

    from world.checks.services import record_consequence_outcome  # noqa: PLC0415

    record_consequence_outcome(
        character_sheet,
        check_type,
        pool,
        _unwrap_consequence(pending),
        breakdown,
        combat_interaction=combat_interaction,
        summary=summary,
    )


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


def _maybe_danger_round_on_bleed_out(character_sheet: CharacterSheet) -> None:
    """Outside combat, dropping into Bleeding-Out ensures a STRICT scene round among
    present characters that ticks the peril (acute, action-driven). In combat, combat
    drives the tick, so this is a no-op."""
    from world.combat.round_context import resolve_combat_round_context  # noqa: PLC0415

    if resolve_combat_round_context(character_sheet) is not None:
        return
    from world.scenes.round_services import ensure_round_for_acute_condition  # noqa: PLC0415

    ensure_round_for_acute_condition(character_sheet)


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


def _apply_wound_tier(  # noqa: PLR0913 - one keyword arg per resolved tier input
    *,
    character_sheet: CharacterSheet,
    result: DamageConsequenceResult,
    wound_check_type: CheckType,
    wound_difficulty: int,
    wound_pool: ConsequencePool,
    extra_modifiers: int,
    combat_interaction_factory: Callable[[], Interaction] | None,
) -> None:
    """Resolve the permanent-wound tier and record any wounds onto ``result``."""
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
        _record_combat_outcome(
            character_sheet,
            wound_check_type,
            wound_pool,
            pending,
            wound_breakdown,
            combat_interaction_factory,
            "permanent wound",
        )


def _apply_death_tier(  # noqa: PLR0913 - one keyword arg per resolved tier input
    *,
    character_sheet: CharacterSheet,
    result: DamageConsequenceResult,
    death_check_type: CheckType,
    death_difficulty: int,
    death_pool: ConsequencePool,
    extra_modifiers: int,
    combat_interaction_factory: Callable[[], Interaction] | None,
    source_character: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM
) -> bool:
    """Resolve the death tier; return True if processing should stop (character dying)."""
    death_breakdown = collect_check_modifiers(character_sheet, death_check_type)
    pending = resolve_vitals_consequence(
        character_sheet,
        death_check_type,
        death_difficulty,
        death_pool,
        extra_modifiers=extra_modifiers + death_breakdown.total,
        source_character=source_character,
    )
    result.modifier_breakdown = death_breakdown
    if _applied_bleed_out(pending):
        result.dying = True
        result.message = "took a lethal hit and is dying"
        _record_combat_outcome(
            character_sheet,
            death_check_type,
            death_pool,
            pending,
            death_breakdown,
            combat_interaction_factory,
            "lethal hit",
        )
        _maybe_danger_round_on_bleed_out(character_sheet)
        return True
    return False


def _apply_knockout_tier(  # noqa: PLR0913 - one keyword arg per resolved tier input
    *,
    character_sheet: CharacterSheet,
    result: DamageConsequenceResult,
    ko_check_type: CheckType,
    knockout_difficulty: int,
    knockout_pool: ConsequencePool,
    extra_modifiers: int,
    combat_interaction_factory: Callable[[], Interaction] | None,
) -> None:
    """Resolve the knockout tier and record an unconscious outcome onto ``result``."""
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
        _record_combat_outcome(
            character_sheet,
            ko_check_type,
            knockout_pool,
            pending,
            ko_breakdown,
            combat_interaction_factory,
            "knockout",
        )


def process_damage_consequences(  # noqa: PLR0913 - each param is a distinct survivability input
    character_sheet: CharacterSheet | None,
    damage_dealt: int,
    damage_type: DamageType | None,
    *,
    extra_modifiers: int = 0,
    combat_interaction_factory: Callable[[], Interaction] | None = None,
    source_character: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM
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
        combat_interaction_factory: Zero-argument callable that returns the
            combat Interaction this resolution belongs to. Invoked only inside a
            firing tier branch (so a whiff never mints an Interaction); it may be
            called more than once when multiple tiers fire, so the caller is
            responsible for memoizing it — the NPC-action path does, so all
            targets of the same action share one Interaction row (#864).
            When None (e.g. the mechanics effect_handlers path), recording is
            skipped — the exactly-one-source constraint forbids a sourceless
            record. Recording is a pure side effect and never changes the
            returned DamageConsequenceResult.
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

    from world.magic.services import survivability_save_baselines  # noqa: PLC0415

    saves = survivability_save_baselines(character_sheet.character)

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
        _apply_wound_tier(
            character_sheet=character_sheet,
            result=result,
            wound_check_type=_ensure_endurance_check_type(),
            wound_difficulty=wound_difficulty,
            wound_pool=wound_pool,
            extra_modifiers=extra_modifiers + saves.wound,
            combat_interaction_factory=combat_interaction_factory,
        )

    # 2. Death check (health <= 0)
    death_difficulty = calculate_death_difficulty(health_pct=raw_health_pct)
    death_pool = _death_pool(damage_type)
    if death_difficulty > 0 and death_pool is not None:
        if _apply_death_tier(
            character_sheet=character_sheet,
            result=result,
            death_check_type=_ensure_death_check_type(),
            death_difficulty=death_difficulty,
            death_pool=death_pool,
            extra_modifiers=extra_modifiers + saves.death,
            combat_interaction_factory=combat_interaction_factory,
            source_character=source_character,
        ):
            return result

    # 3. Knockout check (health between 0% and 20%)
    knockout_difficulty = calculate_knockout_difficulty(
        health_pct=health_pct,
    )
    knockout_pool = _knockout_pool()
    if knockout_difficulty > 0 and knockout_pool is not None:
        _apply_knockout_tier(
            character_sheet=character_sheet,
            result=result,
            ko_check_type=_ensure_endurance_check_type(),
            knockout_difficulty=knockout_difficulty,
            knockout_pool=knockout_pool,
            extra_modifiers=extra_modifiers + saves.knockout,
            combat_interaction_factory=combat_interaction_factory,
        )

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


def _resolve_peril_via_pool(
    character_sheet: CharacterSheet,
    instance: ConditionInstance,
    pool: ConsequencePool,
) -> bool:
    """Resolve an acute-peril ConditionInstance through a guarded consequence pool.

    The shared death-gated core of the acute-peril dying state (#1479): used by
    BOTH the terminal bleed-out path (``_resolve_terminal_bleed_out``, the
    ``bleed_out_terminal`` pool) and the abandonment path (``resolve_abandonment``,
    the source-appropriate ``select_abandonment_pool`` pool). Extracting it keeps
    a single implementation of "roll the peril's authored resist check against a
    death-gated candidate set, then dispatch the selected outcome" (no parallel
    implementations).

    The roll uses the instance's current-stage authored ``resist_check_type`` +
    ``resist_difficulty`` (ADR-0019 — no hardcoded difficulty). The gate
    (``death_is_permitted``) is applied by EXCLUDING every character-loss
    (``die``) candidate before selection when death is not permitted, so a PC
    source, a death_deferred victim, or an absent source can never select death
    (ADR-0023). The selected outcome is dispatched on its ``character_loss``
    flag — the single ``die`` row is the only character-loss candidate, so this
    also covers the fallback outcome produced when the Failure tier is emptied
    by the gate (it is non-loss → survive). Authored survival effects (e.g.
    ``captured_alive``'s CAPTURE effect) are applied by ``apply_resolution``.

    Returns True iff the character died this call. On BOTH death and survival the
    instance's acute-peril condition is removed so that ``_danger_persists``
    returns False and the DANGER round auto-ends (#1479). Any wounds remain on
    the survivor. ``_mark_dead`` stays the single death writer.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        resolve_pool_consequences,
        select_consequence,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.conditions.services import remove_condition  # noqa: PLC0415
    from world.vitals.peril_resolution import death_is_permitted  # noqa: PLC0415

    stage = instance.current_stage
    source_character = instance.source_character
    candidates = resolve_pool_consequences(pool)
    if not death_is_permitted(victim_sheet=character_sheet, source_character=source_character):
        candidates = [c for c in candidates if not c.character_loss]

    # select_consequence + apply_resolution still operate on ObjectDB; walk
    # back at the boundary (mirrors resolve_vitals_consequence).
    character = character_sheet.character
    pending = select_consequence(
        character,
        stage.resist_check_type,
        stage.resist_difficulty,
        candidates,
    )
    apply_resolution(
        pending,
        ResolutionContext(character=character, source_character=source_character),
    )

    selected = pending.selected_consequence
    if selected.character_loss:
        _mark_dead(character_sheet)
        # Clear the acute-peril condition on death too, mirroring the survival branch.
        # This makes _danger_persists return False so the DANGER round auto-ends and
        # the dead victim is never re-classified or re-resolved (#1479).
        remove_condition(character, instance.condition)
        return True

    # Survived (recover / stay_incapacitated / captured / gated-out failure):
    # stop the peril by clearing this instance's condition.
    remove_condition(character, instance.condition)
    return False


def _resolve_terminal_bleed_out(
    character_sheet: CharacterSheet,
    instance: ConditionInstance,
) -> bool:
    """Resolve a terminal-stage Bleeding-Out instance through the guarded pool.

    Replaces the old unconditional ``_mark_dead`` at the terminal stage with a
    death-gated consequence-pool roll (#1479) against the ``bleed_out_terminal``
    pool (recover / stay_incapacitated / die). The gated roll + outcome dispatch
    is the shared ``_resolve_peril_via_pool`` core.

    A missing pool (seeding gap) holds the victim in the dying state — it never
    falls back to unconditional death.
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.vitals.constants import POOL_BLEED_OUT_TERMINAL  # noqa: PLC0415

    pool = ConsequencePool.objects.filter(name=POOL_BLEED_OUT_TERMINAL).first()
    if pool is None:
        # Seeding gap — cannot run the gated resolution. Holding the victim in
        # the dying state is the safe degradation (never kill ungated; #1479).
        return False

    return _resolve_peril_via_pool(character_sheet, instance, pool)


def resolve_abandonment(character_sheet: CharacterSheet | None) -> bool:
    """Resolve an abandoned downed victim's fate through the abandonment pool (#1479 T8).

    Selects the source-appropriate abandonment pool
    (``select_abandonment_pool`` — enemy / pvp / environmental by the peril's
    ``source_character`` kind) and runs the SAME death-gated core as the terminal
    bleed-out path (``_resolve_peril_via_pool``). The roll uses the acute-peril
    instance's current-stage authored ``resist_check_type`` + ``resist_difficulty``
    (ADR-0019).

    No-op (returns False) when the victim no longer carries an acute-peril
    instance with a resolvable stage — i.e. a rescue (the bleed-out cleared via
    ``remove_condition`` / ``perform_treatment``) beats the check. A seeding gap
    (the abandonment pool is absent) likewise holds the victim rather than killing
    them ungated.

    Returns True iff the victim died this call.
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.vitals.peril_resolution import (  # noqa: PLC0415
        acute_peril_instances,
        select_abandonment_pool,
    )

    if character_sheet is None:
        return False

    instance = (
        acute_peril_instances(character_sheet)
        .select_related("current_stage__resist_check_type")
        .first()
    )
    if (
        instance is None
        or instance.current_stage is None
        or instance.current_stage.resist_check_type is None
    ):
        return False

    try:
        pool = select_abandonment_pool(instance.source_character)
    except ConsequencePool.DoesNotExist:
        # Seeding gap — hold the victim rather than resolving ungated (#1479).
        return False

    return _resolve_peril_via_pool(character_sheet, instance, pool)


def _advance_to_next_stage(instance: ConditionInstance, stage: ConditionStage) -> None:
    """Advance ``instance`` to the next higher bleed-out stage, if one exists.

    No-op when ``stage`` is already the highest authored ``stage_order`` for the
    condition (the caller resolves the terminal stage separately).
    """
    from world.conditions.models import ConditionStage  # noqa: PLC0415

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


def advance_bleed_out(character_sheet: CharacterSheet | None) -> bool:
    """Advance staged bleed-out conditions toward death.

    For each active ConditionInstance whose condition.name == BLEED_OUT_CONDITION_NAME:
    - If current_stage is None or has no resist_check_type, skip.
    - At the terminal stage (no higher stage_order exists), resolve through the
      guarded ``bleed_out_terminal`` consequence pool (_resolve_terminal_bleed_out):
      death is reachable only when death_is_permitted; otherwise the victim
      stabilises and the Bleeding-Out condition is cleared.
    - Otherwise perform the resist check at the stage's resist_difficulty and,
      on failure (success_level < 0), advance current_stage to the next higher
      stage_order. On success / non-failure: hold (no change).

    Returns True if the character died during this call, else False.
    """
    from world.conditions.constants import (  # noqa: PLC0415
        BLEED_OUT_CONDITION_NAME,
    )
    from world.conditions.models import (  # noqa: PLC0415
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

        # Terminal stage: resolve through the guarded consequence pool (death is
        # gated by death_is_permitted) instead of an unconditional kill (#1479).
        if _is_terminal_stage(instance):
            if _resolve_terminal_bleed_out(character_sheet, instance):
                return True
            continue

        result = perform_check(
            character,
            stage.resist_check_type,
            target_difficulty=stage.resist_difficulty,
        )

        if int(result.success_level) < 0:
            # Failed resist on a non-terminal stage: advance to the next stage.
            _advance_to_next_stage(instance, stage)

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
    base = vitals.base_max_health
    if base is None:
        base = derive_base_max_health(character_sheet)
    new_max = max(base + thread_addend, 0)
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


def covenant_role_health(character: object, level: int) -> int:  # noqa: OBJECTDB_PARAM
    """Level-scaled covenant-role 'armor': sum of level * bonus_per_level over engaged roles'
    MAX_HEALTH CovenantRoleBonus rows.

    For each covenant role the character is currently ENGAGED in (engaged=True, left_at IS NULL),
    sums ``level * CovenantRoleBonus.bonus_per_level`` where the bonus targets the MAX_HEALTH
    ModifierTarget. One DB query for the bonuses; no query-in-loop.

    Args:
        character: The Character typeclass instance (has .covenant_roles handler).
        level: Character level to scale the bonus against.

    Returns:
        Total covenant-role health armor for this character at the given level.
    """
    from world.covenants.models import CovenantRoleBonus  # noqa: PLC0415
    from world.vitals.constants import MAX_HEALTH_MODIFIER_TARGET  # noqa: PLC0415

    engaged = character.covenant_roles.currently_engaged_roles()
    role_ids = [role.pk for role in engaged]
    if not role_ids:
        return 0
    bonuses = CovenantRoleBonus.objects.filter(
        covenant_role_id__in=role_ids,
        modifier_target__name=MAX_HEALTH_MODIFIER_TARGET,
    )
    return sum(level * bonus.bonus_per_level for bonus in bonuses)


def derive_base_max_health(character_sheet: CharacterSheet) -> int:
    """Derive base_max_health = class stage-rate sum + stamina term + covenant-role armor.

    Reads effective_combat_level so a bonded sidekick's elevation / mentor's cap flow in.

    class_term:    Sum of ClassStageHealthRate.health_per_level for each level 1..effective_level,
                   resolved via stage_for_level(lvl). Zero when no primary class is found.
    stamina_term:  stamina trait value * VitalsConsequenceConfig.stamina_to_health_weight.
    covenant_term: covenant_role_health(character, level) — MAX_HEALTH armor from engaged roles.
    """
    from world.classes.models import CharacterClassLevel, ClassStageHealthRate  # noqa: PLC0415
    from world.classes.services import stage_for_level  # noqa: PLC0415
    from world.covenants.mentorship import effective_combat_level  # noqa: PLC0415
    from world.traits.constants import PrimaryStat  # noqa: PLC0415

    character = character_sheet.character
    level = effective_combat_level(character_sheet)

    primary = (
        CharacterClassLevel.objects.filter(character=character, is_primary=True)
        .select_related("character_class")
        .first()
    )
    class_term = 0
    if primary is not None:
        rates = {
            r.stage: r.health_per_level
            for r in ClassStageHealthRate.objects.filter(character_class=primary.character_class)
        }
        for lvl in range(1, level + 1):
            class_term += rates.get(stage_for_level(lvl), 0)

    cfg = get_vitals_consequence_config()
    stamina = character.traits.get_trait_value(PrimaryStat.STAMINA)
    stamina_term = stamina * cfg.stamina_to_health_weight

    return class_term + stamina_term + covenant_role_health(character, level)


def apply_clamped_chronic_damage(character_sheet: CharacterSheet, amount: int) -> int:
    """Reduce health by ``amount`` but never to/below the knockout floor, never increasing it.

    The long-term tier MUST NOT incapacitate or kill (#520 §5.3): it never calls
    process_damage_consequences and clamps post-damage health strictly above
    KNOCKOUT_HEALTH_THRESHOLD * max_health. Returns the health actually removed.
    """
    if amount <= 0:
        return 0
    try:
        vitals = character_sheet.vitals
    except (AttributeError, ObjectDoesNotExist):
        return 0
    floor = int(KNOCKOUT_HEALTH_THRESHOLD * vitals.max_health) + 1  # strictly above the floor
    new_health = max(vitals.health - amount, floor)
    if new_health >= vitals.health:  # already at/below floor -> never heal, never raise
        return 0
    removed = vitals.health - new_health
    vitals.health = new_health
    vitals.save(update_fields=["health"])
    return removed


def get_vitals_consequence_config() -> VitalsConsequenceConfig:
    """Return the VitalsConsequenceConfig singleton (pk=1), creating it lazily on first call.

    Holds the global knockout pool and the default wound/death pools used when a
    DamageType doesn't specify its own. Configure via the Django admin.
    """
    from world.vitals.models import VitalsConsequenceConfig  # noqa: PLC0415

    cfg, _ = VitalsConsequenceConfig.objects.get_or_create(pk=1)
    return cfg


def resolve_vitals_consequence(  # noqa: PLR0913 - each param is a distinct consequence-pipeline input
    character_sheet: CharacterSheet,
    check_type: CheckTypeHint,
    target_difficulty: int,
    pool: ConsequencePool,
    *,
    extra_modifiers: int = 0,
    source_character: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM
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
    apply_resolution(
        pending,
        ResolutionContext(character=character, source_character=source_character),
    )
    return pending


def _apply_round_tick_damage(
    target: ObjectDB,  # noqa: OBJECTDB_PARAM
    result: RoundTickResult,
) -> None:
    """Apply acute DoT damage from a RoundTickResult to the target's health.

    Mirrors mechanics._deal_damage: decrement health, then run the survivability
    pipeline (acute tier — may wound/knockout/kill, which is correct for in-round
    poison). No-op for targets without vitals. Consults the target's active
    Succor cover (#1744) before any further damage reduction is applied.
    """
    if not result.damage_dealt:
        return
    try:
        sheet = target.sheet_data
        vitals = sheet.vitals
    except (AttributeError, ObjectDoesNotExist):
        return
    from actions.round_context import get_active_round_context  # noqa: PLC0415
    from world.conditions.services import resolve_damage_type_resistance  # noqa: PLC0415
    from world.magic.services import apply_damage_reduction_from_threads  # noqa: PLC0415

    round_ctx = get_active_round_context(sheet)

    for damage_type, amount in result.damage_dealt:
        if amount <= 0:
            continue
        # Succor cover (#1744) — an ally's active shelter this round. Applied first,
        # mirroring how INTERPOSE mitigates pre_payload.amount before any further
        # reduction in the combat-attack path.
        covered_amount = amount
        if round_ctx is not None:
            multiplier = round_ctx.get_cover_for(sheet, damage_type)
            covered_amount = int(amount * multiplier)
            if covered_amount <= 0:
                continue
        effective = (
            apply_damage_reduction_from_threads(target, covered_amount)
            if hasattr(target, "threads")
            else covered_amount
        )
        # Damage-type resistance (condition + gift-thread) via the shared seam (#1588).
        # Closes the asymmetry where DoT damage (poison, burning) ignored resistance.
        effective = resolve_damage_type_resistance(target, effective, damage_type)
        if effective <= 0:
            continue
        vitals.health -= effective
        vitals.save(update_fields=["health"])
        process_damage_consequences(
            character_sheet=target.sheet_data,
            damage_dealt=effective,
            damage_type=damage_type,
        )


def tick_round_for_targets(
    targets: Iterable[ObjectDB],  # noqa: OBJECTDB_PARAM
    *,
    timing: Literal["start", "end"] = ROUND_TICK_END,
) -> None:
    """Apply one round's worth of per-target effects for a set of targets.

    Shared by combat resolve_round/begin_declaration_phase and non-combat scene-round
    resolution so DoT, rounds_remaining/stage countdown, and bleed-out advance through
    one code path. Empty ``targets`` is a no-op — the primitive behind AFK-safety
    (no participants -> no tick). ``timing`` is "start" or "end".
    """
    from world.conditions.services import process_round_end, process_round_start  # noqa: PLC0415

    target_list = [t for t in targets if t is not None]
    for target in target_list:
        if timing == ROUND_TICK_START:
            result = process_round_start(target)
        else:
            result = process_round_end(target)
        _apply_round_tick_damage(target, result)
    if timing == ROUND_TICK_END:
        from world.fatigue.services import tick_fatigue_collapse_for_targets  # noqa: PLC0415

        for target in target_list:
            try:
                sheet = target.sheet_data
            except (AttributeError, ObjectDoesNotExist):
                continue
            advance_bleed_out(sheet)
        # Non-cast over-capacity exhaustion collapse (acute tier, #520 Phase 5).
        tick_fatigue_collapse_for_targets(target_list)
        # Action-driven plummet descent + impact (#1228). Function-local import
        # avoids a circular import (positioning -> vitals).
        from world.areas.positioning.plummet import advance_plummet  # noqa: PLC0415

        advance_plummet(target_list)
