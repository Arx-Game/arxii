"""Tavern games actions (#3292): the open/join/roll/leave seam.

Thin REGISTRY wrappers over ``world.tavern_games.services``; shared by the
web Place-bar game widget and the telnet ``game`` namespace. Every mutation
converges here, no business logic in the command or the viewset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionResult, TargetType
from world.tavern_games.exceptions import TavernGameError

if TYPE_CHECKING:
    from actions.types import ActionContext

_MSG_NO_PERSONA = "You have no active character."


def _active_persona(actor: ObjectDB):
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = actor.character_sheet
    if sheet is None:
        return None
    return active_persona_for_sheet(sheet)


@dataclass
class _TavernGameAction(Action):
    """Shared shape for tavern-game verbs."""

    category: str = "scenes"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF


@dataclass
class OpenGameAction(_TavernGameAction):
    """Open a new table. Kwargs: ``place``, ``game``, ``ante``."""

    key: str = "tavern_game_open"
    name: str = "Open Tavern Game"
    icon: str = "dice-multiple"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.tavern_games.services import open_session  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_PERSONA)
        place = kwargs.get("place")
        game = kwargs.get("game")
        ante = kwargs.get("ante")
        if place is None or game is None or ante is None:
            return ActionResult(success=False, message="Open which game, where, for what ante?")
        try:
            session = open_session(place=place, game=game, persona=persona, ante=int(ante))
        except TavernGameError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"You open a game of {game.name} at {place.name} (ante {ante}).",
            data={"session_id": session.pk},
        )


@dataclass
class JoinGameAction(_TavernGameAction):
    """Ante in and take a seat. Kwargs: ``session``."""

    key: str = "tavern_game_join"
    name: str = "Join Tavern Game"
    icon: str = "cash-plus"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.tavern_games.services import join_session  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_PERSONA)
        session = kwargs.get("session")
        if session is None:
            return ActionResult(success=False, message="Join which game?")
        try:
            join_session(session=session, persona=persona)
        except TavernGameError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"You ante {session.ante} coppers and join the game.",
            data={"session_id": session.pk},
        )


@dataclass
class RollGameAction(_TavernGameAction):
    """Roll the dice for the current hand. Kwargs: ``session``."""

    key: str = "tavern_game_roll"
    name: str = "Roll Tavern Game Dice"
    icon: str = "dice-6"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.tavern_games.services import roll  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_PERSONA)
        session = kwargs.get("session")
        if session is None:
            return ActionResult(success=False, message="Roll at which game?")
        try:
            seat = roll(session=session, persona=persona)
        except TavernGameError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"You roll a {seat.roll_result}!",
            data={"session_id": session.pk, "roll_result": seat.roll_result},
        )


@dataclass
class LeaveGameAction(_TavernGameAction):
    """Leave the table; refunds the seat's ante. Kwargs: ``session``."""

    key: str = "tavern_game_leave"
    name: str = "Leave Tavern Game"
    icon: str = "exit-run"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.tavern_games.services import leave_session  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_PERSONA)
        session = kwargs.get("session")
        if session is None:
            return ActionResult(success=False, message="Leave which game?")
        try:
            leave_session(session=session, persona=persona)
        except TavernGameError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="You leave the table and take back your ante.")
