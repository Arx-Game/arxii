"""Firing round-start events."""

from __future__ import annotations

from flows.constants import EventName
from flows.events.payloads import CombatRoundStartingPayload
from world.combat import services as _svc
from world.combat.models import CombatEncounter
from world.combat.services.combos.combo_detection import detect_available_combos
from world.combat.services.upkeep.upkeep import drain_reactive_upkeep
from world.combat.types import AvailableCombo


def _fire_round_start(enc: CombatEncounter, round_number: int) -> list[AvailableCombo]:
    """Emit COMBAT_ROUND_STARTING, drain upkeep, detect combos.

    Called once at the top of ``resolve_round`` after the DECLARING→RESOLVING
    transition.  Bundles three sequential steps so the caller contributes a
    single statement toward the ``PLR0915`` limit.
    """
    _svc.emit_event(
        EventName.COMBAT_ROUND_STARTING,
        CombatRoundStartingPayload(
            encounter_id=enc.pk,
            round_number=round_number,
        ),
        location=enc.room,
    )
    drain_reactive_upkeep(enc)
    return detect_available_combos(enc, round_number)
