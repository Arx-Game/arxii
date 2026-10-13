"""Opponent defeat and companion falls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flows.constants import EventName
from flows.events.payloads import CharacterIncapacitatedPayload
from world.combat import services as _svc
from world.combat.constants import OpponentStatus
from world.combat.models import CombatOpponent

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def _resolve_opponent_defeat(opponent: CombatOpponent, source_sheet: CharacterSheet | None) -> bool:
    """Resolve whether an opponent at 0 HP is actually defeated.

    Story-criticality check: prevent death if the NPC is load-bearing for a
    story the attacker isn't part of (#1874). When death is prevented, the
    NPC flees instead and ``False`` is returned. Otherwise the opponent's
    status is set to DEFEATED and ``True`` is returned.
    """
    from world.stories.flee_services import flee_story_critical_npc  # noqa: PLC0415
    from world.stories.npc_protection import (  # noqa: PLC0415
        is_death_prevented_by_story,
    )

    npc_sheet = None
    if opponent.objectdb is not None:
        try:
            npc_sheet = opponent.objectdb.sheet_data
        except AttributeError:
            npc_sheet = None
    attacker = source_sheet.character if source_sheet else None
    if npc_sheet is not None and is_death_prevented_by_story(npc_sheet, attacker):
        flee_story_critical_npc(opponent, attacker)
        return False
    opponent.status = OpponentStatus.DEFEATED
    return True


def _emit_companion_fall(opponent: CombatOpponent) -> None:
    """Announce a bonded companion's defeat to the surge engine (#3575).

    Only a companion-backed ALLY opponent (``summoned_by`` set, a live unreleased
    ``Companion`` owning ``objectdb``) emits; a plain summon, a persona-backed NPC
    and every ENEMY stay silent as before. Emits CHARACTER_INCAPACITATED, never
    CHARACTER_KILLED: defeat is not death (#1873 resolves death at encounter end),
    and the KILLED subscribers (asset loss, death deferral) are for people. Both
    events reach ``relationship_spike_handler`` and dedup to one ALLY_FALLEN.
    The "is this ally someone's companion" predicate now lives in
    ``world.companions.services.resolve_bonded_companion`` (#3652), shared with
    the encounter/battle defeat hooks so it is not spelled a third time.
    """
    from world.companions.services import resolve_bonded_companion  # noqa: PLC0415

    if resolve_bonded_companion(opponent) is None:
        return
    room = opponent.encounter.room
    if room is None:
        return
    _svc.emit_event(
        EventName.CHARACTER_INCAPACITATED,
        CharacterIncapacitatedPayload(
            character=opponent.objectdb,
            source_event=EventName.DAMAGE_PRE_APPLY,
        ),
        location=room,
    )
