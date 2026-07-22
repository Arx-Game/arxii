"""Vitals service layer — survivability pipeline.

Handles damage consequences: knockout checks, death checks, and permanent
wound application. System-agnostic — callable by combat, missions, traps,
or any damage source.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
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
    NEVER_TO_FULL_FRACTION,
    PERMANENT_WOUND_THRESHOLD,
    SURVIVABILITY_CHECK_CATEGORY,
    CharacterLifeState,
)
from world.vitals.types import DamageConsequenceResult, WakeResult

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from datetime import datetime

    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from world.battles.models import Battle
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
    from world.scenes.models import Interaction, Scene
    from world.vitals.models import VitalsConsequenceConfig

logger = logging.getLogger(__name__)

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


def conscious_bystander_present(
    room: ObjectDB | None,  # noqa: OBJECTDB_PARAM
    *,
    subject_id: int,
    exclude_ids: frozenset[int] = frozenset(),
) -> bool:
    """True if anyone but ``subject_id`` present in ``room`` is conscious (can_act).

    The shared core of the three "is a conscious bystander present" checks (#1813):
    ``world.areas.positioning.plummet._potential_catcher_present``,
    ``world.vitals.peril_resolution.potential_rescuer_present``, and
    ``world.scenes.sudden_harm._potential_interposer_present``. Each of those stays a
    thin wrapper with its own docstring/signature/parameter name — only their internal
    loop delegates here.

    ``exclude_ids`` additionally omits any character ids the caller wants excluded
    (e.g. a departing mover, or a peril's hostile source) beyond ``subject_id`` —
    resolving which ids to exclude stays with the caller; this function only walks
    the room and checks ``can_act``.
    """
    if room is None:
        return False
    for obj in room.contents:
        if obj.id == subject_id or obj.id in exclude_ids:
            continue
        try:
            sheet = obj.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            continue
        if can_act(sheet):
            return True
    return False


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
    """Get or create the Endurance CheckType, seeding its stamina trait (#1706).

    Used for both knockout and permanent wound resistance checks. The single
    stamina stat leg is the tenet-permitted resist composition; staff may add
    further trait rows via admin. Idempotent — ``get_or_create`` preserves any
    existing staff weight edit on the (check_type, trait) pair.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.checks.models import CheckTypeTrait  # noqa: PLC0415
    from world.traits.factories import StatTraitFactory  # noqa: PLC0415
    from world.traits.models import TraitCategory  # noqa: PLC0415

    check, _ = CheckType.objects.get_or_create(
        name=ENDURANCE_CHECK_NAME,
        defaults={
            "category": _ensure_survival_category(),
            "description": "Resist knockout and permanent wounds.",
        },
    )
    CheckTypeTrait.objects.get_or_create(
        check_type=check,
        trait=StatTraitFactory(name="stamina", category=TraitCategory.PHYSICAL),
        defaults={"weight": Decimal("1.00")},
    )
    return check


def _ensure_death_check_type() -> CheckType:
    """Get or create the Mortal Resolve CheckType, seeding its willpower trait (#1706).

    Used for death resistance when a character is brought below zero health.
    The single willpower stat leg is the tenet-permitted resist composition.
    Idempotent — ``get_or_create`` preserves any existing staff weight edit.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.checks.models import CheckTypeTrait  # noqa: PLC0415
    from world.traits.factories import StatTraitFactory  # noqa: PLC0415
    from world.traits.models import TraitCategory  # noqa: PLC0415

    check, _ = CheckType.objects.get_or_create(
        name=DEATH_CHECK_NAME,
        defaults={
            "category": _ensure_survival_category(),
            "description": "Resist death when brought below zero health.",
        },
    )
    CheckTypeTrait.objects.get_or_create(
        check_type=check,
        trait=StatTraitFactory(name="willpower", category=TraitCategory.META),
        defaults={"weight": Decimal("1.00")},
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


def _record_wound_details(
    character_sheet: CharacterSheet,
    wounds: list[ConditionTemplate],
    damage_dealt: int,
) -> None:
    """Stamp WoundDetails (mend-cap provenance) onto each applied wound instance (#2644).

    Looks up the active instance apply_condition just created for each wound
    template (synchronous — apply_resolution has already run by the time this
    is called). Re-wounding an already-active wound (stacking/refresh reuses
    the same ConditionInstance) accumulates the extra damage onto the same
    WoundDetails row rather than minting a second one — a second grievous hit
    on the same wound legitimately raises its total mend cap.
    """
    if not wounds or damage_dealt <= 0:
        return
    from world.conditions.services import get_active_conditions  # noqa: PLC0415
    from world.vitals.models import WoundDetails  # noqa: PLC0415

    character = character_sheet.character
    for template in wounds:
        instance = get_active_conditions(character, condition=template).first()
        if instance is None:
            continue
        details, created = WoundDetails.objects.get_or_create(
            condition_instance=instance,
            defaults={"damage_taken": damage_dealt},
        )
        if not created:
            details.damage_taken += damage_dealt
            details.save(update_fields=["damage_taken"])


def _apply_wound_tier(  # noqa: PLR0913 - one keyword arg per resolved tier input
    *,
    character_sheet: CharacterSheet,
    result: DamageConsequenceResult,
    wound_check_type: CheckType,
    wound_difficulty: int,
    wound_pool: ConsequencePool,
    extra_modifiers: int,
    combat_interaction_factory: Callable[[], Interaction] | None,
    damage_dealt: int,
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
        _record_wound_details(character_sheet, wounds, damage_dealt)
        _record_combat_outcome(
            character_sheet,
            wound_check_type,
            wound_pool,
            pending,
            wound_breakdown,
            combat_interaction_factory,
            "permanent wound",
        )


@transaction.atomic
def mend_wound(
    healer_sheet: CharacterSheet,  # noqa: ARG001 - signature parity, see docstring
    target_sheet: CharacterSheet,
    wound_instance: ConditionInstance,
    amount: int,
) -> int:
    """Raise a wounded target's health, double-bounded (#2644 — the attrition invariant).

    ``healer_sheet`` is accepted but unused inside this function — kept for
    call-site parity with ``perform_treatment`` (helper, target, effect,
    amount) and reserved for future healer-side provenance/logging on this
    seam; it plays no role in either bound described below.

    Two independent bounds compose to guarantee the party is always net-weaker
    for having fought (ADR-0155):

    - **Bound 1 (here): the never-to-full fraction.** The total ever mended on
      *this* wound, across every healer who has ever tended it, cannot exceed
      ``NEVER_TO_FULL_FRACTION x wound_details.damage_taken``. The remainder
      is permanent attrition, by design.
    - **Bound 2 (one layer up, in ``perform_treatment``):** each healer gets
      exactly one tending per wound, ever (an incompetent healer cannot burn
      the wound's only chance for everyone else) — enforced by
      ``TreatmentAttempt``'s partial UniqueConstraint on
      ``(helper, target_condition_instance)``, not by this function.

    Also clamps to ``target_sheet.vitals.max_health``. Mends
    ``min(amount, remaining_fraction_cap, room_to_max_health)`` — 0 is a legal,
    non-error result (a wound already at its cap, or a target already at full
    health), never an exception.

    Raises:
        NotAWoundError: ``wound_instance`` has no ``WoundDetails`` — it isn't a
            wound (e.g. a plain debuff condition). Never callable outside the
            treatment flow; this is not a general condition-severity API.
    """
    from world.vitals.exceptions import NotAWoundError  # noqa: PLC0415

    try:
        details = wound_instance.wound_details
    except (AttributeError, ObjectDoesNotExist) as exc:
        raise NotAWoundError from exc

    cap_total = int(NEVER_TO_FULL_FRACTION * details.damage_taken)
    remaining_cap = max(0, cap_total - details.health_mended_total)
    if remaining_cap <= 0 or amount <= 0:
        return 0

    vitals = target_sheet.vitals
    room_to_max = max(0, vitals.max_health - vitals.health)
    mended = min(amount, remaining_cap, room_to_max)
    if mended <= 0:
        return 0

    vitals.health += mended
    vitals.save(update_fields=["health"])
    details.health_mended_total += mended
    details.save(update_fields=["health_mended_total"])
    return mended


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
        _stamp_unconscious_wake_deadline(character_sheet)
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
            damage_dealt=damage_dealt,
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

    Also propagates DEAD to the sheet's roster lifecycle_state (#1770 PR2):
    _mark_dead is the single death writer and only fires on the real terminal
    path (death_deferred is gated upstream via death_is_permitted), so this is
    the one seam where combat death reaches CharacterSheet.lifecycle_state.
    """
    try:
        vitals = character_sheet.vitals
    except (AttributeError, ObjectDoesNotExist):
        return
    vitals.life_state = CharacterLifeState.DEAD
    vitals.died_at = timezone.now()
    vitals.died_in_scene = _active_scene_at_body(character_sheet)
    vitals.save(update_fields=["life_state", "died_at", "died_in_scene"])

    # Lazy import per repo convention: vitals must not import roster at module level.
    from world.character_sheets.types import LifecycleState  # noqa: PLC0415
    from world.roster.services.activity import set_lifecycle_state  # noqa: PLC0415

    set_lifecycle_state(character_sheet, LifecycleState.DEAD)
    _deliver_death_condolence(character_sheet)

    # Estate settlement window opens at death (#1985); marriage pacts dissolve
    # (houses' death seam, previously unwired). Lazy imports per the same
    # convention as the roster propagation above.
    from world.estates.services import open_settlement  # noqa: PLC0415

    open_settlement(character_sheet)

    from world.roster.models.families import Kinsperson  # noqa: PLC0415
    from world.societies.houses.services import handle_death_for_pacts  # noqa: PLC0415

    kinsperson = Kinsperson.objects.filter(sheet=character_sheet).first()
    if kinsperson is not None:
        # Succession law and intestacy both read this flag; the death writer is
        # the one place it gets stamped.
        if not kinsperson.is_deceased:
            kinsperson.is_deceased = True
            kinsperson.save(update_fields=["is_deceased"])
        handle_death_for_pacts(kinsperson)


def _active_scene_at_body(character_sheet: CharacterSheet) -> Scene | None:
    """The active scene at the body's location, if any (#2287).

    Bounds the ghost emit window and death-kudos eligibility. None for
    offscreen deaths (no location, no active scene there).
    """
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    character = character_sheet.character
    location = character.location
    if location is None:
        return None
    return get_active_scene(location)


def _deliver_death_condolence(character_sheet: CharacterSheet) -> None:
    """Deliver the OOC condolence moment to the dead character's player (#2287).

    Best-effort on every leg: the character text message (telnet + web log)
    and a ``character_died`` frame to the bound account (web toast). A death
    with nobody online loses nothing — the config text is also shown at next
    login while the ghost interlude lasts (frontend concern).
    """
    config = get_vitals_consequence_config()
    body = config.death_condolence_body
    if not body:
        return
    character = character_sheet.character
    try:
        character.msg(body)
    except Exception:
        logger.exception("death condolence character.msg failed for sheet %s", character_sheet.pk)
    account = character.db_account
    if account is None:
        return
    payload = {"character": character.key, "body": body}
    try:
        account.msg(character_died=((), payload))
    except Exception:
        logger.exception("character_died push failed for account %s", account.pk)


def is_retired(character_sheet: CharacterSheet | None) -> bool:
    """True when the dead character has been released (retire fired, #2287)."""
    if character_sheet is None:
        return False
    try:
        return character_sheet.vitals.retired_at is not None
    except (AttributeError, ObjectDoesNotExist):
        return False


def retire_character(character_sheet: CharacterSheet, *, forced_by: object | None = None) -> None:
    """Release a dead character: the final lock of the ghost interlude (#2287).

    Player-fired when ready, staff-forceable (``forced_by``), and auto-fired by
    the ``vitals.auto_retire`` scheduler task after the grace window. Sets
    ``retired_at`` (idempotent no-op when already set), which closes the
    death-kudos window and blocks any further puppet/login of the character.
    Raises ``ValueError`` for a living character — retire is a death off-ramp,
    not a lifecycle verb (LifecycleState.RETIRED for living retirement is a
    separate, undesigned flow).
    """
    if not is_dead(character_sheet):
        msg = "Only dead characters can be retired."
        raise ValueError(msg)
    vitals = character_sheet.vitals
    if vitals.retired_at is not None:
        return
    vitals.retired_at = timezone.now()
    vitals.save(update_fields=["retired_at"])
    if forced_by is not None:
        logger.info(
            "Character sheet %s retired by staff account %s",
            character_sheet.pk,
            forced_by,
        )
    character = character_sheet.character
    account = character.db_account
    if account is None:
        return
    for session in list(character.sessions.all()):
        try:
            account.unpuppet_object(session)
        except Exception:
            logger.exception("unpuppet on retire failed for sheet %s", character_sheet.pk)


def _resolve_peril_via_pool(
    character_sheet: CharacterSheet,
    instance: ConditionInstance,
    pool: ConsequencePool,
    *,
    death_permitted: bool,
) -> bool:
    """Resolve an acute-peril ConditionInstance through a guarded consequence pool.

    The shared death-gated core of the acute-peril dying state (#1479, generalized for
    #1733): used by the terminal bleed-out path (``_resolve_terminal_bleed_out``), the
    abandonment path (``resolve_abandonment``), and the battle Surrounded terminal path
    (``advance_surrounded``). Extracting it keeps a single implementation of "roll the
    peril's authored resist check against a death-gated candidate set, then dispatch the
    selected outcome" (no parallel implementations).

    ``death_permitted`` is now supplied by the caller rather than derived internally —
    the original gate (``death_is_permitted(source_character=instance.source_character)``)
    assumed every peril source is an ``ObjectDB`` character, which battle Surrounded's
    source (an abstract ``BattleUnit``) never is; a ``None`` source would silently
    default to "not permitted" forever. Bleed-out and abandonment callers compute this
    the same way they always did (see their bodies); Surrounded computes it via
    ``select_surrounded_terminal_pool`` routing instead.

    The roll uses the instance's current-stage authored ``resist_check_type`` +
    ``resist_difficulty`` (ADR-0019 — no hardcoded difficulty). The gate is applied by
    EXCLUDING every character-loss (``die``) candidate before selection when
    ``death_permitted`` is False, so a PC source, a death_deferred victim, or an absent
    source can never select death (ADR-0023). The selected outcome is dispatched on its
    ``character_loss`` flag — the single ``die`` row is the only character-loss
    candidate, so this also covers the fallback outcome produced when the Failure tier is
    emptied by the gate (it is non-loss → survive). Authored survival effects (e.g.
    ``captured_alive``'s CAPTURE effect) are applied by ``apply_resolution``.

    Returns True iff the character died this call. On BOTH death and survival the
    instance's acute-peril condition is removed so that ``_danger_persists`` returns
    False and the DANGER round auto-ends (#1479). Any wounds remain on the survivor.
    ``_mark_dead`` stays the single death writer.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        resolve_pool_consequences,
        select_consequence,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.conditions.services import remove_condition  # noqa: PLC0415

    stage = instance.current_stage
    source_character = instance.source_character
    candidates = resolve_pool_consequences(pool)
    if not death_permitted:
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
    from world.vitals.peril_resolution import death_is_permitted  # noqa: PLC0415

    pool = ConsequencePool.objects.filter(name=POOL_BLEED_OUT_TERMINAL).first()
    if pool is None:
        # Seeding gap — cannot run the gated resolution. Holding the victim in
        # the dying state is the safe degradation (never kill ungated; #1479).
        return False

    death_permitted = death_is_permitted(
        victim_sheet=character_sheet, source_character=instance.source_character
    )
    return _resolve_peril_via_pool(character_sheet, instance, pool, death_permitted=death_permitted)


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
        death_is_permitted,
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

    death_permitted = death_is_permitted(
        victim_sheet=character_sheet, source_character=instance.source_character
    )
    return _resolve_peril_via_pool(character_sheet, instance, pool, death_permitted=death_permitted)


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


def _advance_staged_peril_condition(
    character_sheet: CharacterSheet | None,
    condition_name: str,
    terminal_resolver: Callable[[CharacterSheet, ConditionInstance], bool],
) -> bool:
    """Advance every active instance of a staged acute-peril condition by one round.

    Shared body for ``advance_bleed_out`` and ``advance_surrounded`` (#1733) — the
    staged-resist-check loop (non-terminal: resist check, advance stage on failure;
    terminal: hand off to ``terminal_resolver``) is identical for any staged acute-peril
    condition; only the condition name and the terminal-stage resolution strategy differ.

    Args:
        character_sheet: The character to advance, or None (no-op).
        condition_name: The ``ConditionTemplate.name`` to advance instances of.
        terminal_resolver: Called with (character_sheet, instance) when an instance is at
            its terminal stage; returns True if the character died.

    Returns:
        True if the character died during this call, else False.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import get_active_conditions  # noqa: PLC0415

    if character_sheet is None:
        return False

    # perform_check still operates on ObjectDB; walk back at the boundary.
    # Refactoring that layer is queued for Phase 3 of the OBJECTDB_PARAM rollout.
    character = character_sheet.character

    # Route through get_active_conditions (honors suppression by default) rather
    # than filtering ConditionInstance directly — keeps staged-peril advancement
    # consistent with the rest of the conditions layer when suppression becomes
    # an authored mechanic. Issue #601.
    try:
        template = ConditionTemplate.get_by_name(condition_name)
    except ConditionTemplate.DoesNotExist:
        return False

    instances = list(
        get_active_conditions(character, condition=template).select_related(
            "current_stage__resist_check_type"
        )
    )

    for instance in instances:
        stage = instance.current_stage
        if stage is None or stage.resist_check_type is None:
            continue

        # Terminal stage: resolve through the guarded consequence pool (death is
        # gated by the caller-supplied terminal_resolver) instead of an
        # unconditional kill (#1479).
        if _is_terminal_stage(instance):
            if terminal_resolver(character_sheet, instance):
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


def advance_bleed_out(character_sheet: CharacterSheet | None) -> bool:
    """Advance staged bleed-out conditions toward death.

    Thin wrapper around ``_advance_staged_peril_condition`` for
    ``BLEED_OUT_CONDITION_NAME``, terminal-resolved by ``_resolve_terminal_bleed_out``:
    at the terminal stage (no higher stage_order exists), resolves through the guarded
    ``bleed_out_terminal`` consequence pool — death is reachable only when
    death_is_permitted; otherwise the victim stabilises and the Bleeding-Out condition
    is cleared. See ``_advance_staged_peril_condition`` for the shared staged-resist-
    check mechanics (non-terminal: resist check, advance stage on failure).

    Returns True if the character died during this call, else False.
    """
    from world.conditions.constants import BLEED_OUT_CONDITION_NAME  # noqa: PLC0415

    return _advance_staged_peril_condition(
        character_sheet, BLEED_OUT_CONDITION_NAME, _resolve_terminal_bleed_out
    )


# ---------------------------------------------------------------------------
# Wake arc — unconscious recovery (#2287)
# ---------------------------------------------------------------------------


def unconscious_instance(character_sheet: CharacterSheet | None) -> ConditionInstance | None:
    """Return the character's active Unconscious ConditionInstance, if any."""
    from world.conditions.constants import UNCONSCIOUS_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import get_active_conditions  # noqa: PLC0415

    if character_sheet is None:
        return None
    try:
        template = ConditionTemplate.get_by_name(UNCONSCIOUS_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        return None
    return get_active_conditions(character_sheet.character, condition=template).first()


def get_dream_room() -> ObjectDB | None:  # noqa: OBJECTDB_PARAM - genuinely a room object
    """Return the liminal dream room (seeded by the survivability cluster).

    None on an unseeded database — callers fall back to normal perception.
    """
    from evennia.utils.search import search_tag  # noqa: PLC0415

    from world.vitals.constants import (  # noqa: PLC0415
        DREAM_ROOM_TAG,
        DREAM_ROOM_TAG_CATEGORY,
    )

    rooms = search_tag(key=DREAM_ROOM_TAG, category=DREAM_ROOM_TAG_CATEGORY)
    return rooms[0] if rooms else None


def perceives_dreamside(character_sheet: CharacterSheet | None) -> bool:
    """True when the character's perception is relocated to the dream side (#2287).

    Unconscious characters dream; the dead do NOT — a ghost watches the waking
    room (the ghost interlude), so death always wins over any lingering
    Unconscious instance.

    Sleeping characters also dream (#2290) — voluntary sleep applies the
    Sleeping condition, which broadens dreamside perception.
    """
    if character_sheet is None or is_dead(character_sheet):
        return False
    if unconscious_instance(character_sheet) is not None:
        return True
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import has_condition  # noqa: PLC0415
    from world.vitals.constants import SLEEPING_CONDITION_NAME  # noqa: PLC0415

    sleeping_template = ConditionTemplate.objects.filter(name=SLEEPING_CONDITION_NAME).first()
    if sleeping_template is None:
        return False
    return has_condition(character_sheet.character, sleeping_template)


def calculate_wake_difficulty(*, health_pct: float, rounds_elapsed: int) -> int:
    """Difficulty of the per-round wake check.

    Scales up with missing health and eases per round spent unconscious (and
    therefore eases as healing raises ``health_pct``), floored at 0 — an
    untended character trends toward waking, never away from it.
    """
    config = get_vitals_consequence_config()
    missing_pct = int((1.0 - max(0.0, min(1.0, health_pct))) * 100)
    difficulty = (
        config.wake_base_difficulty
        + missing_pct * config.wake_scaling_per_percent
        - rounds_elapsed * config.wake_ease_per_round
    )
    return max(0, difficulty)


def _stamp_unconscious_wake_deadline(character_sheet: CharacterSheet | None) -> None:
    """Set the guaranteed-wake deadline on a freshly applied Unconscious instance.

    ``expires_at`` doubles as the force-wake backstop: the hourly
    ``conditions.expiration_cleanup`` scheduler task deletes instances past
    their deadline, so an untended character can never be stuck dreamside.
    Only stamps when null (re-knockouts while already unconscious keep the
    earliest deadline).
    """
    from datetime import timedelta  # noqa: PLC0415

    from world.conditions.services import SECONDS_PER_ROUND  # noqa: PLC0415

    instance = unconscious_instance(character_sheet)
    if instance is None or instance.expires_at is not None:
        return
    config = get_vitals_consequence_config()
    instance.expires_at = timezone.now() + timedelta(
        seconds=config.wake_guaranteed_rounds * SECONDS_PER_ROUND
    )
    instance.save(update_fields=["expires_at"])


def _wake_roll_blocked(
    instance: ConditionInstance,
    now: datetime,
    *,
    in_combat_tick: bool,
) -> str | None:
    """The pre-roll gates of attempt_wake: None = roll; a message = blocked.

    Combat ticks: no same-tick roll for an Unconscious applied THIS round —
    "one check per round" means per *elapsed* round. Out of combat: at most
    one roll per wall-clock round-equivalent (stamps the attempt time).
    """
    from world.conditions.services import SECONDS_PER_ROUND  # noqa: PLC0415

    if in_combat_tick:
        if (now - instance.applied_at).total_seconds() < SECONDS_PER_ROUND:
            return ""
        return None
    last = instance.last_resist_attempt_at
    if last is not None and (now - last).total_seconds() < SECONDS_PER_ROUND:
        return "You are still sunk too deep to try again."
    instance.last_resist_attempt_at = now
    instance.save(update_fields=["last_resist_attempt_at"])
    return None


def _maybe_move_to_destination(character: ObjectDB, destination_room: ObjectDB | None) -> None:  # noqa: OBJECTDB_PARAM
    """Move a waking character to their dreamwalk destination (#2290 escape lever).

    Called after a successful wake when ``destination_room`` is provided.
    Uses Evennia's ``move_object`` so room-state broadcasts fire normally.
    """
    if destination_room is None:
        return
    character.location = destination_room
    character.save(update_fields=["db_location"])


def attempt_wake(
    character_sheet: CharacterSheet | None,
    *,
    in_combat_tick: bool = False,
    destination_room: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM
) -> WakeResult:
    """Attempt to wake from Unconscious: one Endurance check per round.

    Difficulty scales with current injury and eases per round unconscious
    (``calculate_wake_difficulty``); past the guaranteed-wake deadline the
    character wakes without a roll. Out of combat the attempt is rate-limited
    to one per ``SECONDS_PER_ROUND`` wall-clock round-equivalent; round ticks
    (``in_combat_tick=True``) get one free roll per round instead. A character
    who is actively Bleeding Out cannot wake — stabilising the dying comes
    first.

    #2290: ``destination_room`` — when provided (the dreamwalk target's physical
    room), the character's body is moved there after waking. This is the escape
    lever: a dreamwalker who reached a bonded dreamer's dreamspace can wake up
    at the target's location instead of their own body's location.
    """
    from world.conditions.services import SECONDS_PER_ROUND, remove_condition  # noqa: PLC0415
    from world.vitals.peril_resolution import acute_peril_instances  # noqa: PLC0415

    instance = unconscious_instance(character_sheet)
    if character_sheet is None or instance is None:
        return WakeResult(attempted=False, woke=False, message="You are already awake.")
    if acute_peril_instances(character_sheet).exists():
        return WakeResult(
            attempted=False,
            woke=False,
            message="You are dying; your body cannot find its way back yet.",
        )
    now = timezone.now()
    character = character_sheet.character
    if instance.expires_at is not None and now >= instance.expires_at:
        remove_condition(character, instance.condition)
        _maybe_move_to_destination(character, destination_room)
        return WakeResult(
            attempted=True, woke=True, message="You claw your way back to consciousness."
        )
    blocked = _wake_roll_blocked(instance, now, in_combat_tick=in_combat_tick)
    if blocked is not None:
        return WakeResult(attempted=False, woke=False, message=blocked)
    rounds_elapsed = int((now - instance.applied_at).total_seconds() // SECONDS_PER_ROUND)
    try:
        health_pct = character_sheet.vitals.health_percentage
    except (AttributeError, ObjectDoesNotExist):
        health_pct = 0.0
    difficulty = calculate_wake_difficulty(health_pct=health_pct, rounds_elapsed=rounds_elapsed)
    check_type = _ensure_endurance_check_type()
    result = perform_check(character, check_type, target_difficulty=difficulty)
    if int(result.success_level) >= 0:
        remove_condition(character, instance.condition)
        _maybe_move_to_destination(character, destination_room)
        return WakeResult(
            attempted=True, woke=True, message="You claw your way back to consciousness."
        )
    return WakeResult(
        attempted=True, woke=False, message="Consciousness slips away from your grasp."
    )


def advance_surrounded(character_sheet: CharacterSheet | None, *, battle: Battle) -> bool:
    """Advance staged Surrounded (battle acute-peril) conditions toward death (#1733).

    Thin wrapper around ``_advance_staged_peril_condition`` for
    ``SURROUNDED_CONDITION_NAME``. Unlike ``advance_bleed_out``, the terminal resolver
    needs ``battle`` — Surrounded's death-permission gate is determined by battle-scoped
    pool routing (``select_surrounded_terminal_pool``, ``world/battles/resolution.py``),
    not ``death_is_permitted``'s ObjectDB-source gate (see Task 2's docstring for why:
    the isolating pressure is an abstract ``BattleUnit``, which has no ``ObjectDB``).

    Returns True if the character died during this call, else False.
    """
    from world.battles.resolution import resolve_surrounded_terminal  # noqa: PLC0415
    from world.conditions.constants import SURROUNDED_CONDITION_NAME  # noqa: PLC0415

    def _terminal(sheet: CharacterSheet, instance: ConditionInstance) -> bool:
        return resolve_surrounded_terminal(character_sheet=sheet, instance=instance, battle=battle)

    return _advance_staged_peril_condition(character_sheet, SURROUNDED_CONDITION_NAME, _terminal)


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

    cfg = VitalsConsequenceConfig.objects.cached_singleton()
    if cfg is None:
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
    from world.magic.services import (  # noqa: PLC0415
        apply_damage_reduction_from_threads,
        coherence_cache_scope,
    )

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
        # coherence_cache_scope memoizes motif_coherence_bonus per (sheet, resonance)
        # so DR + the three save baselines share one wardrobe walk (#1267).
        with coherence_cache_scope():
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
            # #2287: unconscious characters get one free wake roll per round.
            attempt_wake(sheet, in_combat_tick=True)
        # Non-cast over-capacity exhaustion collapse (acute tier, #520 Phase 5).
        tick_fatigue_collapse_for_targets(target_list)
        # Action-driven plummet descent + impact (#1228). Function-local import
        # avoids a circular import (positioning -> vitals).
        from world.areas.positioning.plummet import advance_plummet  # noqa: PLC0415

        advance_plummet(target_list)

        # #2019: expire conjured obstacles + zone hazards in the target rooms.
        # #2209: ramparts expire on the same per-round tick.
        from world.areas.positioning.services import (  # noqa: PLC0415
            expire_obstacle_rounds,
            expire_rampart_rounds,
        )
        from world.room_features.trap_services import tick_zone_hazards  # noqa: PLC0415

        rooms_seen: set[int] = set()
        for target in target_list:
            room = target.db_location
            if room is not None and room.id not in rooms_seen:
                rooms_seen.add(room.id)
                expire_obstacle_rounds(room)
                expire_rampart_rounds(room)
                tick_zone_hazards(room)
