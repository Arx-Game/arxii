"""Telnet ``game`` command: tavern games coin-stakes gambling (#3292).

Grammar:
    game                    - show the open table (if any) at your current place
    game open <game>=<ante> - open a table at your current place
    game join               - ante in and take a seat at the open table there
    game roll                - roll the dice for the current hand
    game leave                - leave the table, taking back your ante

Thin wrapper: every mutation dispatches the matching REGISTRY action from
``actions.definitions.tavern_games`` - the same seam the web Place-bar game
widget uses. No business logic here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.scenes.place_models import Place
    from world.tavern_games.models import GameSession

_USAGE = "Usage:\n  game  |  game open <game name>=<ante>\n  game join  |  game roll  |  game leave"


class CmdGame(ArxCommand):
    """Play a curated coin-stakes tavern game at your current Place."""

    key = "game"
    locks = "cmd:all()"
    help_category = "Social"

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._show()
            return
        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        handler = {
            "open": self._do_open,
            "join": self._do_join,
            "roll": self._do_roll,
            "leave": self._do_leave,
        }.get(subverb)
        if handler is None:
            self.msg(_USAGE)
            return
        try:
            handler(rest)
        except CommandError as err:
            self.msg(str(err))

    def _current_place(self) -> Place:
        from world.scenes.place_models import PlacePresence  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            msg = "No active character."
            raise CommandError(msg)
        persona = active_persona_for_sheet(sheet)
        presence = PlacePresence.objects.filter(persona=persona).select_related("place").first()
        if presence is None:
            msg = "You aren't at a place."
            raise CommandError(msg)
        return presence.place

    def _open_session_here(self) -> GameSession:
        from world.tavern_games.constants import GameSessionState  # noqa: PLC0415
        from world.tavern_games.models import GameSession  # noqa: PLC0415

        place = self._current_place()
        session = (
            GameSession.objects.filter(place=place, state=GameSessionState.OPEN)
            .order_by("-opened_at")
            .first()
        )
        if session is None:
            msg = "There's no open game here. Start one with 'game open <name>=<ante>'."
            raise CommandError(msg)
        return session

    def _show(self) -> None:
        from world.tavern_games.constants import GameSessionState  # noqa: PLC0415
        from world.tavern_games.models import GameSession  # noqa: PLC0415

        place = self._current_place()
        session = (
            GameSession.objects.filter(place=place, state=GameSessionState.OPEN)
            .select_related("game")
            .order_by("-opened_at")
            .first()
        )
        if session is None:
            self.msg("There's no open game here.")
            return
        seats = list(session.seats.select_related("persona"))
        lines = [
            f"|w{session.game.name}|n at {place.name}: ante {session.ante}, pot {session.pot}."
        ]
        for seat in seats:
            status = f"rolled {seat.roll_result}" if seat.roll_result is not None else "waiting"
            lines.append(f"  {seat.persona.name}: {status}")
        self.msg("\n".join(lines))

    def _do_open(self, args: str) -> None:
        from actions.registry import get_action  # noqa: PLC0415
        from world.tavern_games.models import TavernGame  # noqa: PLC0415

        try:
            name_part, ante_part = args.split("=", 1)
        except ValueError as exc:
            msg = "Usage: game open <game name>=<ante>"
            raise CommandError(msg) from exc
        name = name_part.strip()
        try:
            ante = int(ante_part.strip())
        except ValueError as exc:
            msg = "The ante must be a whole number of coppers."
            raise CommandError(msg) from exc
        game = TavernGame.objects.filter(name__iexact=name, is_active=True).first()
        if game is None:
            msg = f"No such game: '{name}'."
            raise CommandError(msg)
        place = self._current_place()
        result = get_action("tavern_game_open").run(
            actor=self.caller, place=place, game=game, ante=ante
        )
        if result.message:
            self.msg(result.message)

    def _do_join(self, _args: str) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        session = self._open_session_here()
        result = get_action("tavern_game_join").run(actor=self.caller, session=session)
        if result.message:
            self.msg(result.message)

    def _do_roll(self, _args: str) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        session = self._open_session_here()
        result = get_action("tavern_game_roll").run(actor=self.caller, session=session)
        if result.message:
            self.msg(result.message)

    def _do_leave(self, _args: str) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        session = self._open_session_here()
        result = get_action("tavern_game_leave").run(actor=self.caller, session=session)
        if result.message:
            self.msg(result.message)
