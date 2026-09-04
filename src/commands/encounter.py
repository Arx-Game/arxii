"""GM combat-encounter lifecycle telnet namespace (#1494, create #3388).

A thin command face for the encounter actions in
``actions.definitions.gm_combat``. Each subverb delegates directly to
``Action().run(actor=self.caller, **kwargs)``. No business logic lives here.
"""

from __future__ import annotations

from commands.exceptions import CommandError
from commands.namespace import ArxNamespaceCommand
from commands.utils.gm_resolution import resolve_position_by_name

_USAGE = (
    "Usage: encounter <subcommand>\n"
    "  encounter create [pace]                 - start a new encounter here (alias: start)\n"
    "  encounter begin                         - begin a new round\n"
    "  encounter resolve                       - resolve the current round\n"
    "  encounter add <name> <tier> [pool [position]]\n"
    "                                           - add an NPC opponent\n"
    "  encounter spawn <template name> [at <position>]\n"
    "                                           - spawn an authored bestiary creature (#3424)\n"
    "  encounter default <tier>                - preview opponent defaults\n"
    "  encounter addpc <character>             - add a PC to the encounter\n"
    "  encounter removepc <participant>        - remove a PC from the encounter\n"
    "  encounter removenpc <opponent>          - remove an NPC opponent (#3382)\n"
    "  encounter pause                         - pause/resume the encounter\n"
    "  encounter end                           - force-end the encounter\n"
    "  encounter stakes <local|regional|national|continental|world>\n"
    "                                           - change stakes level (#3383)\n"
    "  encounter risk <low|moderate|high|extreme|lethal>\n"
    "                                           - change risk level (#3383)\n"
    "  encounter pace <timed|ready|manual>     - change pace mode (#3383)\n"
    "  encounter timer <minutes>               - change the TIMED round timer (#3383)\n"
    "  encounter curve <name|none>            - set or clear the escalation curve (#3552)\n"
    "  encounter duel <character> <name> <tier> <pool>\n"
    "                                           - propose a lethal duel (#3068)"
)

_CREATE_USAGE = "Usage: encounter create [pace]  (pace: timed/ready/manual; default timed)"
_ADD_USAGE = "Usage: encounter add <name> <tier> [pool [position]]"
_SPAWN_USAGE = "Usage: encounter spawn <template name> [at <position>]"
_SPAWN_AT_SEPARATOR = " at "
_DEFAULT_USAGE = "Usage: encounter default <tier>"
_ADDPC_USAGE = "Usage: encounter addpc <character>"
_REMOVEPC_USAGE = "Usage: encounter removepc <participant>"
_REMOVENPC_USAGE = "Usage: encounter removenpc <opponent>"
_DUEL_USAGE = "Usage: encounter duel <character> <name> <tier> <pool>"
_STAKES_USAGE = "Usage: encounter stakes <local|regional|national|continental|world>"
_RISK_USAGE = "Usage: encounter risk <low|moderate|high|extreme|lethal>"
_PACE_USAGE = "Usage: encounter pace <timed|ready|manual>"
_TIMER_USAGE = "Usage: encounter timer <minutes>"
_CURVE_USAGE = "Usage: encounter curve <name|none>"

# Token-count thresholds for argument parsing.
_MIN_ADD_TOKENS = 2
_ADD_POOL_INDEX = 2
_ADD_POSITION_INDEX = 3
_DUEL_TOKENS = 4

_SUBVERB_HANDLERS: dict[str, str] = {
    "create": "_handle_create",
    "start": "_handle_create",
    "begin": "_handle_begin",
    "resolve": "_handle_resolve",
    "add": "_handle_add",
    "spawn": "_handle_spawn",
    "default": "_handle_default",
    "addpc": "_handle_addpc",
    "removepc": "_handle_removepc",
    "removenpc": "_handle_removenpc",
    "pause": "_handle_pause",
    "end": "_handle_end",
    "stakes": "_handle_stakes",
    "risk": "_handle_risk",
    "pace": "_handle_pace",
    "timer": "_handle_timer",
    "curve": "_handle_curve",
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

    def _handle_create(self, rest: str) -> None:
        """Parse ``create [pace]`` and dispatch CreateEncounterAction."""
        from actions.definitions.gm_combat import CreateEncounterAction  # noqa: PLC0415

        pace_mode = rest.split()[0].lower() if rest.strip() else None
        self._run_action(CreateEncounterAction, pace_mode=pace_mode)

    def _handle_begin(self, _rest: str) -> None:
        """Dispatch BeginEncounterRoundAction."""
        from actions.definitions.gm_combat import BeginEncounterRoundAction  # noqa: PLC0415

        self._run_action(BeginEncounterRoundAction)

    def _handle_resolve(self, _rest: str) -> None:
        """Dispatch ResolveEncounterRoundAction."""
        from actions.definitions.gm_combat import ResolveEncounterRoundAction  # noqa: PLC0415

        self._run_action(ResolveEncounterRoundAction)

    def _handle_add(self, rest: str) -> None:
        """Parse ``add <name> <tier> [pool [position]]`` and dispatch AddOpponentAction.

        The position token (#3385) is only parseable once pool is given -- pool is
        already effectively required by ``_resolve_add_opponent_inputs``'s
        validation (``gm_combat.py``) even though this usage string calls it
        optional. Resolved against the encounter's spawn room (the caller's
        current room) via the shared ``resolve_position_by_name`` helper -- the
        same one ``CmdPosition`` uses.
        """
        from actions.definitions.gm_combat import AddOpponentAction  # noqa: PLC0415

        tokens = rest.split()
        if len(tokens) < _MIN_ADD_TOKENS:
            msg = _ADD_USAGE
            raise CommandError(msg)

        name = tokens[0]
        tier = tokens[1]
        threat_pool_id = tokens[_ADD_POOL_INDEX] if len(tokens) > _ADD_POOL_INDEX else None

        kwargs: dict[str, object] = {
            "name": name,
            "tier": tier,
            "threat_pool_id": threat_pool_id,
        }
        if len(tokens) > _ADD_POSITION_INDEX:
            room = self.caller.location
            if room is None:
                msg = "You aren't anywhere."
                raise CommandError(msg)
            position = resolve_position_by_name(room, tokens[_ADD_POSITION_INDEX])
            kwargs["position_id"] = position.pk

        self._run_action(AddOpponentAction, **kwargs)

    def _handle_spawn(self, rest: str) -> None:
        """Parse ``spawn <template name> [at <position>]`` and dispatch SpawnCreatureAction (#3424).

        ``<template name>`` may contain spaces (e.g. "Gorehorn the Undying"), so
        the optional trailing position clause is introduced by the literal
        `` at `` token rather than positional token-splitting (contrast
        ``_handle_add``, whose NPC name is single-token). The position name
        resolves against the caller's current room via the shared
        ``resolve_position_by_name`` helper -- the same one ``_handle_add`` and
        ``CmdPosition`` use.
        """
        from actions.definitions.gm_combat import SpawnCreatureAction  # noqa: PLC0415

        text = rest.strip()
        if not text:
            raise CommandError(_SPAWN_USAGE)

        template_name = text
        position_name = ""
        if _SPAWN_AT_SEPARATOR in text:
            template_name, _, position_name = text.partition(_SPAWN_AT_SEPARATOR)
            template_name = template_name.strip()
            position_name = position_name.strip()

        if not template_name:
            raise CommandError(_SPAWN_USAGE)

        kwargs: dict[str, object] = {"template": template_name}
        if position_name:
            room = self.caller.location
            if room is None:
                msg = "You aren't anywhere."
                raise CommandError(msg)
            position = resolve_position_by_name(room, position_name)
            kwargs["position_id"] = position.pk

        self._run_action(SpawnCreatureAction, **kwargs)

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

    def _handle_stakes(self, rest: str) -> None:
        """Parse ``stakes <level>`` and dispatch UpdateEncounterSettingsAction (#3383)."""
        from actions.definitions.gm_combat import UpdateEncounterSettingsAction  # noqa: PLC0415

        level = self._require_arg(rest, _STAKES_USAGE)
        self._run_action(UpdateEncounterSettingsAction, stakes_level=level.split()[0])

    def _handle_risk(self, rest: str) -> None:
        """Parse ``risk <level>`` and dispatch UpdateEncounterSettingsAction (#3383)."""
        from actions.definitions.gm_combat import UpdateEncounterSettingsAction  # noqa: PLC0415

        level = self._require_arg(rest, _RISK_USAGE)
        self._run_action(UpdateEncounterSettingsAction, risk_level=level.split()[0])

    def _handle_pace(self, rest: str) -> None:
        """Parse ``pace <mode>`` and dispatch UpdateEncounterSettingsAction (#3383)."""
        from actions.definitions.gm_combat import UpdateEncounterSettingsAction  # noqa: PLC0415

        mode = self._require_arg(rest, _PACE_USAGE)
        self._run_action(UpdateEncounterSettingsAction, pace_mode=mode.split()[0])

    def _handle_timer(self, rest: str) -> None:
        """Parse ``timer <minutes>`` and dispatch UpdateEncounterSettingsAction (#3383)."""
        from actions.definitions.gm_combat import UpdateEncounterSettingsAction  # noqa: PLC0415

        minutes = self._require_arg(rest, _TIMER_USAGE)
        self._run_action(UpdateEncounterSettingsAction, pace_timer_minutes=minutes.split()[0])

    def _handle_curve(self, rest: str) -> None:
        """Parse ``curve <name|none>`` and dispatch UpdateEncounterSettingsAction (#3552)."""
        from actions.definitions.gm_combat import UpdateEncounterSettingsAction  # noqa: PLC0415

        name = self._require_arg(rest, _CURVE_USAGE)
        self._run_action(UpdateEncounterSettingsAction, escalation_curve=name.strip())

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
