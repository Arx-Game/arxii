"""GM combat-encounter lifecycle telnet namespace (#1494).

A thin command face for the eight encounter actions in
``actions.definitions.gm_combat``. Each subverb delegates directly to
``Action().run(actor=self.caller, **kwargs)``. No business logic lives here.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = (
    "Usage: encounter <subcommand>\n"
    "  encounter begin                         — begin a new round\n"
    "  encounter resolve                       — resolve the current round\n"
    "  encounter add <name> <tier> [pool]      — add an NPC opponent\n"
    "  encounter default <tier>                — preview opponent defaults\n"
    "  encounter addpc <character>             — add a PC to the encounter\n"
    "  encounter removepc <participant>        — remove a PC from the encounter\n"
    "  encounter pause                         — pause/resume the encounter\n"
    "  encounter end                           — force-end the encounter"
)

_ADD_USAGE = "Usage: encounter add <name> <tier> [pool]"
_DEFAULT_USAGE = "Usage: encounter default <tier>"
_ADDPC_USAGE = "Usage: encounter addpc <character>"
_REMOVEPC_USAGE = "Usage: encounter removepc <participant>"

# Token-count thresholds for argument parsing.
_MIN_ADD_TOKENS = 2
_ADD_POOL_INDEX = 2

_SUBVERB_HANDLERS: dict[str, str] = {
    "begin": "_handle_begin",
    "resolve": "_handle_resolve",
    "add": "_handle_add",
    "default": "_handle_default",
    "addpc": "_handle_addpc",
    "removepc": "_handle_removepc",
    "pause": "_handle_pause",
    "end": "_handle_end",
}


class CmdEncounter(ArxCommand):
    """Manage an active combat encounter in your current room.

    All subcommands are gated by the encounter's scene GM or staff status in the
    backing action layer.
    """

    key = "encounter"
    aliases = ()
    locks = "cmd:all()"
    action = None  # Routed manually by subverb.

    def func(self) -> None:
        """Route the leading subverb to the appropriate action."""
        raw = (self.args or "").strip()
        if not raw:
            self.msg(_USAGE)
            return

        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        handler_name = _SUBVERB_HANDLERS.get(subverb)
        if handler_name is None:
            self.msg(_USAGE)
            return

        try:
            getattr(self, handler_name)(rest)
        except CommandError as err:
            self.msg(str(err))

    def _run_action(self, action_cls: type[Any], **kwargs: Any) -> None:
        """Instantiate *action_cls* and forward the result message."""
        result = action_cls().run(actor=self.caller, **kwargs)
        if result.message:
            self.msg(result.message)

    def _require_arg(self, value: str, usage: str) -> str:
        """Return a stripped token or raise CommandError with *usage*."""
        token = value.strip()
        if not token:
            msg = usage
            raise CommandError(msg)
        return token

    def _handle_begin(self, _rest: str) -> None:
        """Dispatch BeginEncounterRoundAction."""
        from actions.definitions.gm_combat import BeginEncounterRoundAction  # noqa: PLC0415

        self._run_action(BeginEncounterRoundAction)

    def _handle_resolve(self, _rest: str) -> None:
        """Dispatch ResolveEncounterRoundAction."""
        from actions.definitions.gm_combat import ResolveEncounterRoundAction  # noqa: PLC0415

        self._run_action(ResolveEncounterRoundAction)

    def _handle_add(self, rest: str) -> None:
        """Parse ``add <name> <tier> [pool]`` and dispatch AddOpponentAction."""
        from actions.definitions.gm_combat import AddOpponentAction  # noqa: PLC0415

        tokens = rest.split()
        if len(tokens) < _MIN_ADD_TOKENS:
            msg = _ADD_USAGE
            raise CommandError(msg)

        name = tokens[0]
        tier = tokens[1]
        threat_pool_id = tokens[_ADD_POOL_INDEX] if len(tokens) > _ADD_POOL_INDEX else None

        self._run_action(
            AddOpponentAction,
            name=name,
            tier=tier,
            threat_pool_id=threat_pool_id,
        )

    def _handle_default(self, rest: str) -> None:
        """Parse ``default <tier>`` and dispatch PreviewOpponentDefaultsAction."""
        from actions.definitions.gm_combat import PreviewOpponentDefaultsAction  # noqa: PLC0415

        tier = self._require_arg(rest, _DEFAULT_USAGE)
        self._run_action(PreviewOpponentDefaultsAction, tier=tier.split()[0])

    def _handle_addpc(self, rest: str) -> None:
        """Parse ``addpc <character>`` and dispatch AddEncounterParticipantAction."""
        from actions.definitions.gm_combat import AddEncounterParticipantAction  # noqa: PLC0415

        character_sheet_id = self._require_arg(rest, _ADDPC_USAGE)
        self._run_action(
            AddEncounterParticipantAction,
            character_sheet_id=character_sheet_id.split()[0],
        )

    def _handle_removepc(self, rest: str) -> None:
        """Parse ``removepc <participant>`` and dispatch RemoveEncounterParticipantAction."""
        from actions.definitions.gm_combat import RemoveEncounterParticipantAction  # noqa: PLC0415

        participant_id = self._require_arg(rest, _REMOVEPC_USAGE)
        self._run_action(
            RemoveEncounterParticipantAction,
            participant_id=participant_id.split()[0],
        )

    def _handle_pause(self, _rest: str) -> None:
        """Dispatch PauseEncounterAction."""
        from actions.definitions.gm_combat import PauseEncounterAction  # noqa: PLC0415

        self._run_action(PauseEncounterAction)

    def _handle_end(self, _rest: str) -> None:
        """Dispatch EndEncounterAction."""
        from actions.definitions.gm_combat import EndEncounterAction  # noqa: PLC0415

        self._run_action(EndEncounterAction)
