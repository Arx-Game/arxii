"""Recording NPC regard when a character defeats an NPC."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.types import ActionOutcome

if TYPE_CHECKING:
    pass


def _maybe_record_npc_regard_on_defeat(
    participant: CombatParticipant,
    action: CombatRoundAction,
    target: CombatOpponent | None,
    outcome: ActionOutcome,
) -> None:
    """Record a PC_FOILED_NPC_PLAN regard event when a PC defeats a notable NPC.

    #2039 — a persona-backed NPC opponent defeated by a PC records a regard
    event. A mook/persona-less opponent's defeat is deliberately a no-op.
    """
    if target is None or target.persona_id is None:
        return
    defeated = any(
        dr.opponent_id == target.pk and dr.defeated
        for dr in outcome.damage_results
        if hasattr(dr, "opponent_id")
    )
    if not defeated:
        return
    from world.npc_services.constants import NpcRegardEventReason  # noqa: PLC0415
    from world.npc_services.regard import (  # noqa: PLC0415
        get_regard_event_config,
        record_npc_regard_event,
    )
    from world.scenes.models import Persona  # noqa: PLC0415

    try:
        pc_persona = participant.character_sheet.primary_persona
    except Persona.DoesNotExist:
        pc_persona = None
    if pc_persona is not None:
        cfg = get_regard_event_config()
        record_npc_regard_event(
            holder_persona=target.persona,
            target=pc_persona,
            amount=cfg.combat_defeat_amount,
            reason=NpcRegardEventReason.PC_FOILED_NPC_PLAN,
            source_pc_combat_action=action,
        )
