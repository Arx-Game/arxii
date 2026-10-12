"""Updating an encounter's settings."""

from __future__ import annotations

import logging

from django.utils import timezone

from world.combat.constants import PaceMode
from world.combat.models import CombatEncounter, EscalationCurve
from world.combat.services.encounter.readiness import maybe_resolve_on_ready
from world.scenes.constants import RoundStatus

logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)

# Tri-state sentinel for optional "leave unchanged" kwargs (#3552); mirrors
# world/skills/services.py's _UNSET.
_UNSET = object()


def update_encounter_settings(  # noqa: PLR0913 - keyword-only tri-state settings kwargs
    encounter: CombatEncounter,
    *,
    stakes_level: str | None = None,
    risk_level: str | None = None,
    pace_mode: str | None = None,
    pace_timer_minutes: int | None = None,
    escalation_curve: EscalationCurve | None | object = _UNSET,
) -> CombatEncounter:
    """GM-driven mid-encounter settings change (#3383, curve #3552).

    Any subset of the fields may be given; omitted fields are left unchanged.
    ``escalation_curve`` is tri-state: omitted (``_UNSET``) leaves it alone,
    ``None`` clears it and tears down the room spike triggers, a curve sets it
    (the idempotent install in ``begin_declaration_phase`` picks it up next
    round). Applies decisions 5-6 of #3383: entering TIMED while DECLARING resets
    round_started_at; every call ends with a maybe_resolve_on_ready check
    (a no-op unless pace_mode is now READY and status is DECLARING).

    Stakes/risk changes gate only future opponent spawns and read-live
    call sites (EncounterAftermathRule lookup at completion,
    StakesEscalationModifier per-tick) - already-spawned CombatOpponent stat
    blocks are never retroactively rescaled (decision 1).
    """
    update_fields = []
    entering_timed = (
        pace_mode == PaceMode.TIMED
        and encounter.pace_mode != PaceMode.TIMED
        and encounter.status == RoundStatus.DECLARING
    )
    if stakes_level is not None:
        encounter.stakes_level = stakes_level
        update_fields.append("stakes_level")
    if risk_level is not None:
        encounter.risk_level = risk_level
        update_fields.append("risk_level")
    if pace_mode is not None:
        encounter.pace_mode = pace_mode
        update_fields.append("pace_mode")
    if pace_timer_minutes is not None:
        encounter.pace_timer_minutes = pace_timer_minutes
        update_fields.append("pace_timer_minutes")
    if escalation_curve is not _UNSET:
        encounter.escalation_curve = escalation_curve
        update_fields.append("escalation_curve")
    if entering_timed:
        encounter.round_started_at = timezone.now()
        update_fields.append("round_started_at")
    if update_fields:
        encounter.save(update_fields=update_fields)
    if escalation_curve is None:
        from world.combat.escalation import remove_escalation_room_triggers  # noqa: PLC0415

        remove_escalation_room_triggers(encounter)
    maybe_resolve_on_ready(encounter)
    return encounter
