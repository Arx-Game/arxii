"""After-fight allegiance actions (#4091): send a won-over NPC away.

Sending a charmed/turned/calmed NPC away ends the hold outright (R2, Decision
20): a named NPC is dropped off the map (``location = None`` — NPCs usually
have no home location to return it to; a GM places it again) and has the
designating allegiance condition lifted via ``remove_condition`` (task 12 fix
round 1 — the hold really ends, not just the body). An ephemeral nameless NPC
(``combat_opponent_id``) is deleted via the shared ``delete_won_over_npc``
guard (identity-map-safe; never a bare ``.delete()`` or a class-wide cache
flush); when that delete is refused (a corrupt row caught by its own Layer-5
guard), execution falls back to the named-NPC path instead of reporting a
success that didn't happen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import Prerequisite
from actions.types import TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext, ActionResult
    from world.combat.models import CombatOpponent
    from world.conditions.models import ConditionTemplate


def _resolve_send_away_target(kwargs: dict) -> tuple[ObjectDB | None, CombatOpponent | None]:
    """(NPC body, CombatOpponent or None) from ``combat_opponent_id`` or
    ``target_persona_id``."""
    from world.combat.models import CombatOpponent  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    opponent_id = kwargs.get("combat_opponent_id")
    if opponent_id:
        opponent = CombatOpponent.objects.filter(pk=opponent_id).select_related("objectdb").first()
        return (opponent.objectdb if opponent else None), opponent
    persona = (
        Persona.objects.filter(pk=kwargs.get("target_persona_id"))
        .select_related("character_sheet__character")
        .first()
    )
    return (persona.character_sheet.character if persona else None), None


def _display_name(body: ObjectDB) -> str:
    """Player-facing name for ``body``: its presented persona, or (an
    ephemeral/persona-less combat mook) its own ``ObjectDB`` key — same
    fallback convention as ``settle_allegiance`` / the allegiance-lapse sweep
    (``world/npc_services/allegiance_outcomes.py``). Never ``str(participant)``.
    """
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    return persona_names_for_sheets([body.pk]).get(body.pk, body.key)


def _drop_named_npc(body: ObjectDB, condition: ConditionTemplate | None) -> None:
    """The named-NPC send-away path: drop off the map and lift the hold.

    NPCs usually have no home location -- a GM places this one again.
    ``condition`` is the designating allegiance condition (or ``None`` if the
    hold had already lapsed); when present, ``remove_condition`` actually ends
    it, so sending someone away is not just a location change (#4091 task 12
    fix round 1 ruling 4). Also the fallback when an ephemeral delete is
    refused (ruling 2) -- same drop, same hold removal, either way in.
    """
    from world.conditions.services import remove_condition  # noqa: PLC0415

    body.location = None
    body.save()
    if condition is not None:
        remove_condition(body, condition)


#: A player character can't be "sent away" like a hireling (#4091 task 12).
#: Canonical PC/NPC test per ``is_player_character``
#: (``world/roster/services/activity.py``) -- an active ``RosterTenure`` OR a
#: live puppet; ``db_account`` alone reads None for an OFFLINE PC, since
#: Evennia's ``unpuppet_object`` clears it. Never matched on a name.
_NOT_AN_NPC_SEND_AWAY_MESSAGE = "They have a will of their own; you cannot send them away."


@dataclass
class HoldsAllegianceOverTargetPrerequisite(Prerequisite):
    """The target carries an allegiance hold the actor applied (#4091)."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from world.npc_services.allegiance import (  # noqa: PLC0415
            ALLEGIANCE_HOLD_KINDS,
            actor_holds_sway_present,
        )
        from world.roster.services.activity import is_player_character  # noqa: PLC0415

        body, _opponent = _resolve_send_away_target((context or {}).get("kwargs", {}))
        if (
            body is None
            or body.db_location_id is None
            or body.db_location_id != actor.db_location_id
        ):
            return False, "They are not here."
        sheet = body.character_sheet
        if sheet is not None and is_player_character(sheet):
            return False, _NOT_AN_NPC_SEND_AWAY_MESSAGE
        if not actor_holds_sway_present(actor, body, kinds=ALLEGIANCE_HOLD_KINDS):
            return False, "They are not under your sway."
        return True, ""


@dataclass
class SendAwayAction(Action):
    """Send an NPC under your sway out of the scene (Decision 20)."""

    key: str = "send_away"
    name: str = "Send away"
    icon: str = "door-open"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HoldsAllegianceOverTargetPrerequisite()]

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.combat.won_over import delete_won_over_npc  # noqa: PLC0415
        from world.npc_services.allegiance import (  # noqa: PLC0415
            ALLEGIANCE_HOLD_KINDS,
            allegiance_sourced_by,
        )
        from world.scenes.narrator import narrate_room_outcome  # noqa: PLC0415

        body, opponent = _resolve_send_away_target(kwargs)
        room = body.location
        name = _display_name(body)
        actor_name = _display_name(actor)
        # PLACEHOLDER (#4091): system-authored line, not player prose.
        narrate_room_outcome(room, f"{name} leaves at {actor_name}'s word.")

        instance = allegiance_sourced_by(body, actor, kinds=ALLEGIANCE_HOLD_KINDS)
        condition = instance.condition if instance is not None else None
        if opponent is not None and opponent.objectdb_is_ephemeral:
            # Deleting the ephemeral ObjectDB cascades its ConditionInstance rows --
            # no separate remove_condition call needed on that path.
            deleted = delete_won_over_npc(opponent)
            if not deleted:
                # Fix round 1: a refused delete (Layer-5 guard) must not report a
                # success that didn't happen -- fall back to the named-NPC path.
                _drop_named_npc(body, condition)
        else:
            _drop_named_npc(body, condition)
        return _ActionResult(success=True, message=f"You send {name} away.")


send_away = SendAwayAction()
