"""Creating a new encounter and its opening state."""

from __future__ import annotations

from world.combat.models import CombatEncounter


def finalize_new_encounter(encounter: CombatEncounter) -> None:
    """Apply the post-creation defaults every "scene-anchored, no explicit room" creation
    caller needs (#3388).

    Extracted from the web ViewSet's ``perform_create`` (#3067) so telnet's
    ``CreateEncounterAction`` gets identical defaulting behavior instead of a second,
    drifting copy. Defaults ``room`` from ``encounter.scene.location`` when the caller
    didn't supply one — every OTHER encounter-creation call site (world.combat.duels,
    world.combat.cast_seed) always threads an explicit room; this is the one shape where
    the caller doesn't have one yet — then assigns the default EscalationCurve via
    ``assign_default_escalation_curve``. An explicit room already set on ``encounter``
    before this call always wins (unchanged from the pre-extraction behavior).
    """
    from world.combat.escalation import assign_default_escalation_curve  # noqa: PLC0415

    if encounter.room_id is None and encounter.scene.location_id is not None:
        encounter.room = encounter.scene.location
        encounter.save(update_fields=["room"])
    assign_default_escalation_curve(encounter)
