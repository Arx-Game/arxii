"""Game-content seeding for the battles app (#1710)."""

from __future__ import annotations


def seed_champion_duel_outcome_wiring() -> None:
    """Seed the ENCOUNTER_COMPLETED -> Champion-duel-outcome TriggerDefinition (#1710).

    Creates (get_or_create) the ``encounter_completed_champion_duel_outcome``
    FlowDefinition (one CALL_SERVICE_FUNCTION step -> apply_champion_duel_outcome)
    and its TriggerDefinition. Idempotent. The per-room Trigger is installed
    at duel-open time by ``open_champion_duel`` (via
    ``install_champion_duel_trigger``), not here.
    """
    from world.battles.duel_wiring import wire_champion_duel_trigger  # noqa: PLC0415

    wire_champion_duel_trigger()
