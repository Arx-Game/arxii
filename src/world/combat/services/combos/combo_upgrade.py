"""Upgrading an action into a combo and reverting it."""

from __future__ import annotations

from world.combat.models import CombatEncounter, CombatRoundAction, ComboDefinition
from world.combat.services.combos.combo_detection import (
    _available_combo_for_action,
    _combo_composition_is_eligible,
    detect_available_combos,
)


def _revalidate_combo_upgrades(
    encounter: CombatEncounter,
    round_number: int,
    actions: dict[int, CombatRoundAction],
) -> None:
    """Clear upgrades whose complete composition is no longer valid.

    This is deliberately done after all declarations and late auto-declarations
    are loaded, rather than trusting the declaration-time upgrade.  Changed
    targets, removed contributors, and lost agency therefore cannot grant a
    combo rider at resolution.
    """
    available = {item.combo.pk: item for item in detect_available_combos(encounter, round_number)}
    for action in actions.values():
        combo_id = action.combo_upgrade_id
        if combo_id is None:
            continue
        candidate = available.get(combo_id)
        valid = False
        if candidate is not None:
            valid = any(match.action.pk == action.pk for match in candidate.slot_matches)
            if valid:
                valid = _combo_composition_is_eligible(candidate)
        if not valid:
            action.combo_upgrade = None
            action.save(update_fields=["combo_upgrade_id"])


def upgrade_action_to_combo(
    action: CombatRoundAction,
    combo: ComboDefinition,
) -> None:
    """Mark a currently eligible PC action as upgraded to a combo.

    The scanner is the authoritative source for slot matching.  Callers get a
    ``ValueError`` instead of being able to persist an arbitrary combo FK.

    Args:
        action: The CombatRoundAction to upgrade.
        combo: The ComboDefinition being activated.

    Raises:
        ValueError: If the current team declarations do not complete *combo*.
    """
    if _available_combo_for_action(action, combo) is None:
        msg = "Combo is not available for this declared action."
        raise ValueError(msg)
    action.combo_upgrade = combo
    action.save(update_fields=["combo_upgrade_id"])


def revert_combo_upgrade(action: CombatRoundAction) -> None:
    """Remove a combo upgrade from a round action, reverting to normal.

    Args:
        action: The CombatRoundAction to revert.
    """
    action.combo_upgrade = None
    action.save(update_fields=["combo_upgrade_id"])
