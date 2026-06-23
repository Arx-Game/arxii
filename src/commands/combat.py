"""Technique cast command — scene-adaptive telnet shell for CastTechniqueAction.

Routes through the SCENE_ADAPTIVE backend so it works both inside and outside
combat:
- Outside combat: ``dispatch_player_action`` runs ``CastTechniqueAction.execute()``
  immediately (non-combat cast via ``request_technique_cast``).
- Inside a DECLARING combat round: ``dispatch_player_action`` calls
  ``CastTechniqueAction.round_declaration()`` which builds a ``CombatRoundAction``
  declaration row; the round resolves when all participants have declared.

Target resolution is context-sensitive:
- Combat context (``_combat_participant_or_none()`` returns non-None):
  ``at <name>`` is resolved as a ``CombatOpponent`` → ``focused_opponent_target_id``.
- Non-combat context: ``at <name>`` is resolved as a ``Persona`` → ``target_persona_id``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef
    from world.combat.models import CombatParticipant

# Keyword prefix used to parse effort=<level> from command args.
_EFFORT_PREFIX = "effort="


class CmdDeclareTechnique(DispatchCommand):
    """Cast a technique — works both in and out of combat.

    Usage:
        cast <technique> [at <target>] [effort=<level>]
        declare <technique> [at <target>] [effort=<level>]

    Outside combat: casts the technique immediately in the active scene.
    In a DECLARING combat round: declares the technique for this round;
    the round resolves once all participants have declared.

    Optionally focus a specific target with ``at <name>`` and set your effort
    level with ``effort=<level>`` (very_low/low/medium/high/extreme;
    defaults to medium).
    """

    key = "cast"
    aliases = ["declare"]
    locks = "cmd:all()"

    # -- Parsed state cached on first call to resolve_action_ref ---------------

    _technique_name: str | None = None
    _target_name: str | None = None
    _effort: str = "medium"
    _parsed: bool = False
    _participant: CombatParticipant | None = None

    # --------------------------------------------------------------------------

    def _parse_args(self) -> None:
        """Parse ``self.args`` once; cache technique name, optional target, effort."""
        if self._parsed:
            return

        import re  # noqa: PLC0415

        from world.fatigue.constants import EffortLevel  # noqa: PLC0415

        raw = (self.args or "").strip()
        if not raw:
            msg = "Usage: cast <technique> [at <target>] [effort=<level>]"
            raise CommandError(msg)

        # Strip off effort=<level> if present (rightmost keyword=value pair).
        effort_str: str = EffortLevel.MEDIUM
        if _EFFORT_PREFIX in raw.lower():
            # Split case-insensitively so "Effort=HIGH" is handled correctly.
            parts = re.split(re.escape(_EFFORT_PREFIX), raw, flags=re.IGNORECASE)
            raw = parts[0].strip()
            effort_val = parts[1].strip().lower()
            valid_values = {v.value for v in EffortLevel}
            if effort_val not in valid_values:
                choices = "/".join(sorted(valid_values))
                msg = f"Invalid effort level '{effort_val}'. Choose from: {choices}"
                raise CommandError(msg)
            effort_str = effort_val

        # Split on the first " at " (case-insensitive) to separate technique from
        # the optional target. A literal search avoids a backtracking-prone regex.
        at_index = raw.lower().find(" at ")
        if at_index != -1:
            self._technique_name = raw[:at_index].strip()
            self._target_name = raw[at_index + len(" at ") :].strip()
        else:
            self._technique_name = raw.strip()
            self._target_name = None

        if not self._technique_name:
            msg = "Usage: cast <technique> [at <target>] [effort=<level>]"
            raise CommandError(msg)

        self._effort = effort_str
        self._parsed = True

    # -- Resolution helpers ----------------------------------------------------

    def _combat_participant_or_none(self) -> CombatParticipant | None:
        """Return the caller's active CombatParticipant in a DECLARING encounter, or None.

        Unlike ``_active_participant`` (which raises), this returns ``None`` when the
        caller is not in an active DECLARING combat round so the non-combat path can
        proceed without branching the dispatch regime.
        """
        from world.combat.constants import EncounterStatus, ParticipantStatus  # noqa: PLC0415
        from world.combat.models import CombatParticipant  # noqa: PLC0415

        return (
            CombatParticipant.objects.filter(
                character_sheet=self.caller.sheet_data,
                status=ParticipantStatus.ACTIVE,
                encounter__status=EncounterStatus.DECLARING,
            )
            .select_related("encounter")
            .order_by("-encounter__created_at")
            .first()
        )

    def _active_participant(self) -> CombatParticipant:
        """Return the caller's active CombatParticipant in a DECLARING encounter.

        Raises:
            CommandError: If no active DECLARING combat is found.
        """
        participant = self._combat_participant_or_none()
        if participant is None:
            msg = "You are not in an active combat round."
            raise CommandError(msg)
        return participant

    def _resolve_technique_id(self) -> int:
        """Return the pk of the technique named by ``self._technique_name``.

        Matches case-insensitively against ``Technique.name`` for techniques
        the caller knows (via ``CharacterTechnique``).

        Raises:
            CommandError: If no matching known technique is found.
        """
        from world.magic.models import CharacterTechnique  # noqa: PLC0415

        name = self._technique_name or ""
        ct = (
            CharacterTechnique.objects.filter(
                character=self.caller.sheet_data,
                technique__name__iexact=name,
            )
            .select_related("technique")
            .first()
        )
        if ct is None:
            msg = f"You don't know a technique called '{name}'."
            raise CommandError(msg)
        return ct.technique_id

    def _resolve_opponent_target_id(self) -> int | None:
        """Return the pk of the CombatOpponent named by ``self._target_name``.

        Scoped to the caller's active encounter so stale/cross-encounter ids
        cannot be targeted.

        Returns ``None`` when no target name was provided (untargeted cast).

        Raises:
            CommandError: If a target name was given but no matching active
                opponent was found.
        """
        if not self._target_name:
            return None

        from world.combat.constants import OpponentStatus  # noqa: PLC0415
        from world.combat.models import CombatOpponent  # noqa: PLC0415

        # Reuse the participant cached by resolve_action_ref; fall back to querying.
        participant = (
            self._participant if self._participant is not None else self._active_participant()
        )
        name = self._target_name
        matches = list(
            CombatOpponent.objects.filter(
                encounter=participant.encounter,
                status=OpponentStatus.ACTIVE,
                name__iexact=name,
            )
        )
        if not matches:
            msg = f"No active opponent named '{name}' in this encounter."
            raise CommandError(msg)
        if len(matches) > 1:
            msg = f"More than one opponent named '{name}' — be more specific."
            raise CommandError(msg)
        return matches[0].pk

    def _resolve_target_persona_id(self) -> int | None:
        """Return the pk of the Persona named by ``self._target_name``, or None.

        Used on the non-combat path when ``at <name>`` names a scene participant.

        Raises:
            CommandError: If a target name was given but no matching Persona exists.
        """
        if not self._target_name:
            return None
        from world.scenes.models import Persona  # noqa: PLC0415

        name = self._target_name
        persona = Persona.objects.filter(name__iexact=name).first()
        if persona is None:
            msg = f"No persona named '{name}' found."
            raise CommandError(msg)
        return persona.pk

    # -- DispatchCommand interface ---------------------------------------------

    def resolve_action_ref(self) -> ActionRef:
        """Build a SCENE_ADAPTIVE ``ActionRef`` for the named technique.

        Parses args on the first call and caches the results so
        ``resolve_action_args`` can reuse them without re-parsing.

        Routes through the SCENE_ADAPTIVE backend so the dispatcher decides
        whether to run immediately (non-combat) or defer as a round declaration
        (inside a DECLARING combat round) — no gating on active combat here.
        """
        from actions.constants import ActionBackend  # noqa: PLC0415
        from actions.types import ActionRef  # noqa: PLC0415

        self._parse_args()
        technique_id = self._resolve_technique_id()
        return ActionRef(
            backend=ActionBackend.SCENE_ADAPTIVE,
            registry_key="cast_technique",
            technique_id=technique_id,
        )

    def resolve_action_args(self) -> dict[str, Any]:
        """Return dispatch kwargs; routes target resolution by context.

        Always includes ``effort_level``.  If ``at <target>`` was given:
        - Combat context → ``focused_opponent_target_id`` (CombatOpponent pk).
        - Non-combat context → ``target_persona_id`` (Persona pk).
        """
        self._parse_args()
        kwargs: dict[str, Any] = {"effort_level": self._effort}

        if not self._target_name:
            return kwargs

        # Check whether we're in a DECLARING combat round to decide how to
        # resolve the target name. Cache the participant for _resolve_opponent_target_id.
        participant = self._combat_participant_or_none()
        if participant is not None:
            self._participant = participant
            opp_id = self._resolve_opponent_target_id()
            if opp_id is not None:
                kwargs["focused_opponent_target_id"] = opp_id
        else:
            persona_id = self._resolve_target_persona_id()
            if persona_id is not None:
                kwargs["target_persona_id"] = persona_id

        return kwargs
