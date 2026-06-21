"""Combat-related telnet commands — thin adapters over the COMBAT dispatch backend.

Commands here parse text input from telnet clients and delegate entirely to
``dispatch_player_action``. No business logic lives here; validation and round
gating are the dispatcher's job.
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
    """Declare a technique for the current combat round.

    Usage:
        cast <technique> [at <target>] [effort=<level>]
        declare <technique> [at <target>] [effort=<level>]

    Declare which technique you will cast this round. Optionally focus
    a specific opponent target with ``at <name>`` and set your effort
    level with ``effort=<level>`` (very_low/low/medium/high/extreme;
    defaults to medium).

    You must be in an active combat round (DECLARING phase) to use this.
    """

    key = "cast"
    aliases = ["declare"]
    locks = "cmd:all()"

    # -- Parsed state cached on first call to resolve_action_ref ---------------

    _technique_name: str | None = None
    _target_name: str | None = None
    _effort: str | None = None
    _parsed: bool = False

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
            parts = raw.rsplit(_EFFORT_PREFIX, 1)
            raw = parts[0].strip()
            effort_val = parts[1].strip().lower()
            valid_values = {v.value for v in EffortLevel}
            if effort_val not in valid_values:
                choices = "/".join(sorted(valid_values))
                msg = f"Invalid effort level '{effort_val}'. Choose from: {choices}"
                raise CommandError(msg)
            effort_str = effort_val

        # Split on " at " (case-insensitive) to separate technique from optional target.
        match = re.match(r"^(.+?)\s+at\s+(.+)$", raw, flags=re.IGNORECASE)
        if match:
            self._technique_name = match.group(1).strip()
            self._target_name = match.group(2).strip()
        else:
            self._technique_name = raw.strip()
            self._target_name = None

        if not self._technique_name:
            msg = "Usage: cast <technique> [at <target>] [effort=<level>]"
            raise CommandError(msg)

        self._effort = effort_str
        self._parsed = True

    # -- Resolution helpers ----------------------------------------------------

    def _active_participant(self) -> CombatParticipant:
        """Return the caller's active CombatParticipant in a DECLARING encounter.

        Raises:
            CommandError: If no active DECLARING combat is found.
        """
        from world.combat.constants import EncounterStatus, ParticipantStatus  # noqa: PLC0415
        from world.combat.models import CombatParticipant  # noqa: PLC0415

        participant = (
            CombatParticipant.objects.filter(
                character_sheet=self.caller.sheet_data,
                status=ParticipantStatus.ACTIVE,
                encounter__status=EncounterStatus.DECLARING,
            )
            .select_related("encounter")
            .order_by("-encounter__created_at")
            .first()
        )
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

        participant = self._active_participant()
        name = self._target_name
        opponent = CombatOpponent.objects.filter(
            encounter=participant.encounter,
            status=OpponentStatus.ACTIVE,
            name__iexact=name,
        ).first()
        if opponent is None:
            msg = f"No active opponent named '{name}' in this encounter."
            raise CommandError(msg)
        return opponent.pk

    # -- DispatchCommand interface ---------------------------------------------

    def resolve_action_ref(self) -> ActionRef:
        """Build a COMBAT ``ActionRef`` for the declared technique.

        Parses args on the first call and caches the results so
        ``resolve_action_args`` can reuse them without re-parsing.
        """
        from actions.constants import ActionBackend  # noqa: PLC0415
        from actions.types import ActionRef  # noqa: PLC0415

        self._parse_args()
        technique_id = self._resolve_technique_id()
        return ActionRef(backend=ActionBackend.COMBAT, technique_id=technique_id)

    def resolve_action_args(self) -> dict[str, Any]:
        """Return dispatch kwargs for the COMBAT backend.

        Keys:
            effort_level: EffortLevel value string (default ``"medium"``).
            focused_opponent_target_id: CombatOpponent pk, omitted when no
                ``at <target>`` was given.
        """
        self._parse_args()
        opp_id = self._resolve_opponent_target_id()
        kwargs: dict[str, Any] = {"effort_level": self._effort}
        if opp_id is not None:
            kwargs["focused_opponent_target_id"] = opp_id
        return kwargs
