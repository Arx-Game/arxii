"""Vitals service layer — survivability pipeline.

Handles damage consequences: knockout checks, death checks, and permanent
wound application. System-agnostic — callable by combat, missions, traps,
or any damage source.
"""

from __future__ import annotations

import logging
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
    CharacterLifeState,
    CharacterStatus,
)
from world.vitals.types import DamageConsequenceResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.conditions.models import ConditionInstance, ConditionTemplate, DamageType

logger = logging.getLogger(__name__)


def is_dead(character: ObjectDB) -> bool:
    """Return True if the character's mortality marker is DEAD.

    Returns False when the character has no vitals row (e.g., NPCs not yet
    set up with health tracking).
    """
    try:
        return character.sheet_data.vitals.life_state == CharacterLifeState.DEAD
    except (AttributeError, ObjectDoesNotExist):
        return False


def is_alive(character: ObjectDB) -> bool:
    """Return True if the character is not dead.

    Convenience inverse of is_dead. A character with no vitals row is
    considered alive (same defensive assumption as is_dead returning False).
    """
    return not is_dead(character)


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

    # Deferred imports — vitals→conditions cross-domain; same pattern as advance_bleed_out.
    from world.conditions.constants import (  # noqa: PLC0415 — vitals→conditions cross-domain deferred import
        BLEED_OUT_CONDITION_NAME,
        UNCONSCIOUS_CONDITION_NAME,
    )

    # Dead characters are exempt from further consequences.
    # Unconscious/dying characters (now conditions) CAN still take damage.
    if is_dead(character):
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
            _apply_consequence_condition(character, BLEED_OUT_CONDITION_NAME)
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
            _apply_consequence_condition(character, UNCONSCIOUS_CONDITION_NAME)
            result.knocked_out = True
            result.final_status = CharacterStatus.UNCONSCIOUS
            result.message = "was knocked unconscious"
            return result

    result.final_status = CharacterStatus.ALIVE
    return result


def _apply_consequence_condition(character: ObjectDB, name: str) -> ConditionInstance | None:
    """Apply a named condition template to character, with graceful degradation.

    Looks up the ConditionTemplate by name. If the template is not found (e.g.,
    on a fresh DB without authored content), this is a no-op — combat must not
    crash on unseeded environments. If found, delegates to apply_condition.

    Args:
        character: The character to apply the condition to.
        name: The condition template name constant (e.g., UNCONSCIOUS_CONDITION_NAME).

    Returns:
        The applied ConditionInstance, or None if the template was not found or
        apply_condition did not create an instance.
    """
    from world.conditions.models import (  # noqa: PLC0415 — vitals→conditions cross-domain deferred import
        ConditionTemplate,
    )
    from world.conditions.services import (  # noqa: PLC0415 — vitals→conditions cross-domain deferred import
        apply_condition,
    )

    template = ConditionTemplate.objects.filter(name=name).first()
    if template is None:
        logger.debug(
            "process_damage_consequences: condition template %r not found; skipping apply",
            name,
        )
        return None
    result = apply_condition(character, template)
    return result.instance


def _is_terminal_stage(instance: ConditionInstance) -> bool:
    """Return True when instance.current_stage is the last stage for its condition.

    A stage is terminal when no stage with a higher stage_order exists for the
    same ConditionTemplate.
    """
    from world.conditions.models import ConditionStage  # noqa: PLC0415 — avoids circular import

    if instance.current_stage is None:
        return False
    return not ConditionStage.objects.filter(
        condition=instance.condition,
        stage_order__gt=instance.current_stage.stage_order,
    ).exists()


def _mark_dead(character: ObjectDB) -> None:
    """Stamp life_state=DEAD and died_at on the character's vitals row.

    No-op when the character has no vitals row (defensive; callers should
    gate on vitals existing before calling advance_bleed_out).
    """
    try:
        vitals = character.sheet_data.vitals
    except (AttributeError, ObjectDoesNotExist):
        return
    vitals.life_state = CharacterLifeState.DEAD
    vitals.died_at = timezone.now()
    vitals.save(update_fields=["life_state", "died_at"])


def advance_bleed_out(character: ObjectDB) -> bool:
    """Advance staged bleed-out conditions toward death.

    For each active ConditionInstance whose condition.name == BLEED_OUT_CONDITION_NAME:
    - If current_stage is None or has no resist_check_type, skip.
    - Perform the resist check at the stage's resist_difficulty.
    - On failure (success_level < 0):
        - If this is the terminal stage (no higher stage_order exists), call
          _mark_dead(character) and return True.
        - Otherwise advance current_stage to the next higher stage_order and save.
    - On success / non-failure: hold (no change).

    Returns True if the character died during this call, else False.
    """
    from world.conditions.constants import (  # noqa: PLC0415 — vitals→conditions cross-domain deferred import
        BLEED_OUT_CONDITION_NAME,
    )
    from world.conditions.models import (  # noqa: PLC0415 — vitals→conditions cross-domain deferred import
        ConditionInstance,
        ConditionStage,
    )

    instances = list(
        ConditionInstance.objects.filter(
            target=character,
            condition__name=BLEED_OUT_CONDITION_NAME,
        ).select_related("condition", "current_stage", "current_stage__resist_check_type")
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
                _mark_dead(character)
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
