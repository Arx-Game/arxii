"""Sustained-action absorption budget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.checks.services import perform_check_with_modifiers
from world.combat.constants import (
    SUSTAINED_BASE_ABSORPTION,
    SUSTAINED_MAX_ABSORPTION,
    SUSTAINED_MIN_ABSORPTION,
)
from world.combat.models import CombatParticipant
from world.combat.services.encounter.check_types import get_concentration_check_type

if TYPE_CHECKING:
    from world.traits.models import CheckOutcome


def roll_sustained_absorption_budget(
    participant: CombatParticipant,
) -> tuple[int, CheckOutcome | None]:
    """Roll Concentration once to set a sustained action's absorption budget (#2705).

    Uses ``perform_check_with_modifiers`` — NOT plain ``perform_check`` — because
    only the ``_with_modifiers`` wrapper calls ``collect_check_modifiers``, which
    folds in ``ConditionCheckModifier`` rows via ``condition_contributions``. 26
    authored Concentration modifier rows exist across the lore fixtures (blinded,
    stressed, focused, etc.) and they are the entire payoff of rolling this check
    at all — a plain ``perform_check`` call would silently make every one of them
    inert for sustained actions.

    ``budget = clamp(SUSTAINED_BASE_ABSORPTION + result.success_level, MIN, MAX)``.
    The clamp exists because ``CheckOutcome.success_level`` is an authored
    -10..+10 field with no lore fixture pinning its ladder (no ``CheckOutcome``
    row is authored in the lore repo at all — they're built ad hoc by seeds/
    factories with varying ranges). Without the clamp a wide authored ladder
    would produce an absurd absorption budget; clamping to
    ``[SUSTAINED_MIN_ABSORPTION, SUSTAINED_MAX_ABSORPTION]`` preserves the
    spec's intended ladder (Crit Fail 0 ... Crit Success 4) under any chart.

    Returns the clamped budget and the CheckOutcome the roll produced (or None
    if the check produced no outcome), so the caller can snapshot the outcome
    on the SustainedAction row.
    """
    result = perform_check_with_modifiers(
        participant.character_sheet.character,
        get_concentration_check_type(),
        target_difficulty=0,
    )
    budget = max(
        SUSTAINED_MIN_ABSORPTION,
        min(SUSTAINED_MAX_ABSORPTION, SUSTAINED_BASE_ABSORPTION + result.success_level),
    )
    return budget, result.outcome
