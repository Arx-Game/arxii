"""After-fight allegiance actions (#4091): send a won-over NPC away.

Sending a charmed/turned/calmed NPC away ends the hold outright (R2, Decision
20): a named NPC is dropped off the map (``location = None`` — NPCs usually
have no home location to return it to; a GM places it again), and an
ephemeral nameless NPC (``combat_opponent_id``) is deleted via the shared
``delete_won_over_npc`` guard (identity-map-safe; never a bare ``.delete()``
or a class-wide cache flush).
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


@dataclass
class HoldsAllegianceOverTargetPrerequisite(Prerequisite):
    """The target carries an allegiance hold the actor applied (#4091)."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from world.conditions.constants import Allegiance  # noqa: PLC0415
        from world.npc_services.allegiance import allegiance_sourced_by  # noqa: PLC0415

        body, _opponent = _resolve_send_away_target((context or {}).get("kwargs", {}))
        if body is None or body.db_location_id != actor.db_location_id:
            return False, "They are not here."
        kinds = frozenset({Allegiance.ALLY_OF_CASTER, Allegiance.TURNED, Allegiance.NEUTRAL})
        if allegiance_sourced_by(body, actor, kinds=kinds) is None:
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
        from world.scenes.narrator import narrate_room_outcome  # noqa: PLC0415

        body, opponent = _resolve_send_away_target(kwargs)
        room = body.location
        name = _display_name(body)
        actor_name = _display_name(actor)
        # PLACEHOLDER (#4091): system-authored line, not player prose.
        narrate_room_outcome(room, f"{name} leaves at {actor_name}'s word.")
        if opponent is not None and opponent.objectdb_is_ephemeral:
            delete_won_over_npc(opponent)
        else:
            body.location = None  # NPCs usually have no home; a GM places it again
            body.save()
        return _ActionResult(success=True, message=f"You send {name} away.")


send_away = SendAwayAction()
