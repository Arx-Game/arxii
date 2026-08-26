"""GM combat-encounter lifecycle telnet namespace (#1494).

A thin command face for the encounter actions in
``actions.definitions.gm_combat``. Each subverb delegates directly to
``Action().run(actor=self.caller, **kwargs)``. No business logic lives here.
"""

from __future__ import annotations

from commands.exceptions import CommandError
from commands.namespace import ArxNamespaceCommand

_USAGE = (
    "Usage: encounter <subcommand>\n"
    "  encounter begin                         - begin a new round\n"
    "  encounter resolve                       - resolve the current round\n"
    "  encounter add <name> <tier> [pool]      - add an NPC opponent\n"
    "  encounter default <tier>                - preview opponent defaults\n"
    "  encounter addpc <character>             - add a PC to the encounter\n"
    "  encounter removepc <participant>        - remove a PC from the encounter\n"
    "  encounter removenpc <opponent>          - remove an NPC opponent (#3382)\n"
    "  encounter pause                         - pause/resume the encounter\n"
    "  encounter end                           - force-end the encounter\n"
    "  encounter duel <character> <name> <tier> <pool>\n"
    "                                           - propose a lethal duel (#3068)"
)

_ADD_USAGE = "Usage: encounter add <name> <tier> [pool]"
_DEFAULT_USAGE = "Usage: encounter default <tier>"
_ADDPC_USAGE = "Usage: encounter addpc <character>"
_REMOVEPC_USAGE = "Usage: encounter removepc <participant>"
_REMOVENPC_USAGE = "Usage: encounter removenpc <opponent>"
_DUEL_USAGE = "Usage: encounter duel <character> <name> <tier> <pool>"

# Token-count thresholds for argument parsing.
_MIN_ADD_TOKENS = 2
_ADD_POOL_INDEX = 2
_DUEL_TOKENS = 4

_SUBVERB_HANDLERS: dict[str, str] = {
    "begin": "_handle_begin",
    "resolve": "_handle_resolve",
    "add": "_handle_add",
    "default": "_handle_default",
    "addpc": "_handle_addpc",
    "removepc": "_handle_removepc",
    "removenpc": "_handle_removenpc",
    "pause": "_handle_pause",
    "end": "_handle_end",
    "duel": "_handle_duel",
}


class CmdEncounter(ArxNamespaceCommand):
    """Manage an active combat encounter in your current room.

    All subcommands are gated by the encounter's scene GM or staff status in the
    backing action layer.
    """

    key = "encounter"
    aliases = ()
    locks = "cmd:all()"
    _USAGE = _USAGE
    _SUBVERB_HANDLERS = _SUBVERB_HANDLERS

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

    def _handle_removenpc(self, rest: str) -> None:
        """Parse ``removenpc <opponent>`` and dispatch RemoveOpponentAction (#3382)."""
        from actions.definitions.gm_combat import RemoveOpponentAction  # noqa: PLC0415

        opponent_id = self._require_arg(rest, _REMOVENPC_USAGE)
        self._run_action(
            RemoveOpponentAction,
            opponent_id=opponent_id.split()[0],
        )

    def _handle_pause(self, _rest: str) -> None:
        """Dispatch PauseEncounterAction."""
        from actions.definitions.gm_combat import PauseEncounterAction  # noqa: PLC0415

        self._run_action(PauseEncounterAction)

    def _handle_end(self, _rest: str) -> None:
        """Dispatch EndEncounterAction."""
        from actions.definitions.gm_combat import EndEncounterAction  # noqa: PLC0415

        self._run_action(EndEncounterAction)

    def _handle_duel(self, rest: str) -> None:
        """Parse ``duel <character> <name> <tier> <pool>`` and propose a lethal duel (#3068).

        Creates a PENDING lethal DuelChallenge against the named PC — no
        encounter exists until they accept it via ``duel accept`` (#1492).
        """
        from actions.definitions.duels import ProposeLethalDuelAction  # noqa: PLC0415

        tokens = rest.split()
        if len(tokens) < _DUEL_TOKENS:
            msg = _DUEL_USAGE
            raise CommandError(msg)

        character_sheet_id, opponent_name, tier, threat_pool_id = tokens[:_DUEL_TOKENS]

        self._run_action(
            ProposeLethalDuelAction,
            character_sheet_id=character_sheet_id,
            opponent_name=opponent_name,
            tier=tier,
            threat_pool_id=threat_pool_id,
        )
