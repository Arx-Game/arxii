"""Vitals service layer — survivability pipeline.

Handles damage consequences: knockout checks, death checks, and permanent
wound application. System-agnostic — callable by combat, missions, traps,
or any damage source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from world.checks.services import perform_check
from world.vitals.constants import (
    DEATH_BASE_DIFFICULTY,
    DEATH_HEALTH_THRESHOLD,
    DEATH_SCALING_PER_PERCENT,
    KNOCKOUT_BASE_DIFFICULTY,
    KNOCKOUT_HEALTH_THRESHOLD,
    KNOCKOUT_SCALING_PER_PERCENT,
    PERMANENT_WOUND_THRESHOLD,
    WOUND_BASE_DIFFICULTY,
    WOUND_SCALING_PER_PERCENT,
    CharacterStatus,
)
from world.vitals.types import DamageConsequenceResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.conditions.models import ConditionTemplate, DamageType


def calculate_knockout_difficulty(*, health_pct: float) -> int:
    """Scale knockout check difficulty by how far below 20% health.

    Returns 0 if above threshold (no check needed).
    """
    if health_pct > KNOCKOUT_HEALTH_THRESHOLD:
        return 0
    pct_below = int((KNOCKOUT_HEALTH_THRESHOLD - health_pct) * 100)
    return KNOCKOUT_BASE_DIFFICULTY + (pct_below * KNOCKOUT_SCALING_PER_PERCENT)


def calculate_death_difficulty(*, health_pct: float) -> int:
    """Scale death check difficulty by depth of negative health.

    Returns 0 if above zero (no check needed).
    """
    if health_pct > DEATH_HEALTH_THRESHOLD:
        return 0
    pct_below = int(abs(health_pct) * 100)
    return DEATH_BASE_DIFFICULTY + (pct_below * DEATH_SCALING_PER_PERCENT)


def calculate_wound_difficulty(*, damage: int, max_health: int) -> int:
    """Scale wound check difficulty by how far damage exceeds 50% threshold.

    Returns 0 if below threshold (no check needed).
    """
    if max_health <= 0:
        return 0
    damage_pct = damage / max_health
    if damage_pct < PERMANENT_WOUND_THRESHOLD:
        return 0
    pct_over = int((damage_pct - PERMANENT_WOUND_THRESHOLD) * 100)
    return WOUND_BASE_DIFFICULTY + (pct_over * WOUND_SCALING_PER_PERCENT)


def process_damage_consequences(  # noqa: PLR0913 — survivability pipeline needs all params
    character: ObjectDB,
    damage_dealt: int,
    damage_type: DamageType | None,
    *,
    knockout_check_type: CheckType | None = None,
    death_check_type: CheckType | None = None,
    wound_check_type: CheckType | None = None,
    extra_modifiers: int = 0,
) -> DamageConsequenceResult:
    """Process survivability consequences after damage is applied.

    Checks thresholds in order: permanent wound, death, knockout.
    Each uses perform_check with scaled difficulty so character stats,
    conditions, and modifiers always influence the outcome.

    Call AFTER writing the health change to CharacterVitals.

    Args:
        character: The damaged character (ObjectDB).
        damage_dealt: How much damage was dealt this hit.
        damage_type: Type of damage (for wound pool routing).
        knockout_check_type: CheckType for knockout resistance.
        death_check_type: CheckType for death resistance.
        wound_check_type: CheckType for wound resistance.
        extra_modifiers: Additional modifiers (fatigue, conditions, etc.).
    """
    try:
        vitals = character.sheet_data.vitals
    except (AttributeError, ObjectDoesNotExist):
        return DamageConsequenceResult(message="No vitals found")

    if vitals.status != CharacterStatus.ALIVE:
        return DamageConsequenceResult(
            final_status=vitals.status,
            message="Character is not alive",
        )

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
    if wound_difficulty > 0 and wound_check_type:
        wound_result = perform_check(
            character,
            wound_check_type,
            target_difficulty=wound_difficulty,
            extra_modifiers=extra_modifiers,
        )
        if wound_result.outcome and wound_result.outcome.success_level <= 0:
            wound = _select_and_apply_wound(character, damage_type)
            if wound:
                result.wounds_applied.append(wound)

    # 2. Death check (health <= 0)
    death_difficulty = calculate_death_difficulty(health_pct=raw_health_pct)
    if death_difficulty > 0 and death_check_type:
        death_result = perform_check(
            character,
            death_check_type,
            target_difficulty=death_difficulty,
            extra_modifiers=extra_modifiers,
        )
        if death_result.outcome and death_result.outcome.success_level <= 0:
            vitals.status = CharacterStatus.DYING
            vitals.dying_final_round = True
            vitals.save(update_fields=["status", "dying_final_round"])
            result.dying = True
            result.dying_final_round = True
            result.final_status = CharacterStatus.DYING
            result.message = "took a lethal hit and is dying"
            return result

    # 3. Knockout check (health between 0% and 20%)
    knockout_difficulty = calculate_knockout_difficulty(
        health_pct=health_pct,
    )
    if knockout_difficulty > 0 and knockout_check_type:
        ko_result = perform_check(
            character,
            knockout_check_type,
            target_difficulty=knockout_difficulty,
            extra_modifiers=extra_modifiers,
        )
        if ko_result.outcome and ko_result.outcome.success_level <= 0:
            vitals.status = CharacterStatus.UNCONSCIOUS
            vitals.unconscious_at = timezone.now()
            vitals.save(update_fields=["status", "unconscious_at"])
            result.knocked_out = True
            result.final_status = CharacterStatus.UNCONSCIOUS
            result.message = "was knocked unconscious"
            return result

    result.final_status = CharacterStatus.ALIVE
    return result


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


def _select_and_apply_wound(
    character: ObjectDB,  # noqa: ARG001 — stub pending wound pool content
    damage_type: DamageType | None,  # noqa: ARG001 — stub pending wound pool content
) -> ConditionTemplate | None:
    """Select and apply a permanent wound from the appropriate pool.

    Routes to damage-type-specific wound pools. Returns the applied
    ConditionTemplate, or None if no pool is configured.

    Stub for Phase 3 — wound pool routing logic will be fleshed out
    as content is created. The infrastructure is ready.
    """
    return None
