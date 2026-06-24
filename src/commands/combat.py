"""Combat telnet commands — scene-adaptive cast and clash-commit shells.

``CmdDeclareTechnique`` (key ``cast``, alias ``declare``)
---------------------------------------------------------
Routes through the SCENE_ADAPTIVE backend so it works both inside and outside
combat:
- Outside combat: ``dispatch_player_action`` runs ``CastTechniqueAction.execute()``
  immediately (non-combat cast via ``request_technique_cast``).
- Inside a DECLARING combat round: ``dispatch_player_action`` calls
  ``CastTechniqueAction.round_declaration()`` which builds a ``CombatRoundAction``
  declaration row; the round resolves when all participants have declared.

Target resolution is context-sensitive:
- Combat context (``_combat_participant_or_none()`` returns non-None):
  ``at <name>`` is resolved by the technique's own targeting relationship
  (``derive_target_relationship``): ENEMY → ``CombatOpponent`` →
  ``focused_opponent_target_id``; ALLY/SELF → ``CombatParticipant`` →
  ``focused_ally_target_id``.
- Non-combat context: ``at <name>`` is resolved as a ``Persona`` → ``target_persona_id``.

The optional ``secondary`` keyword declares the technique in its derived passive
slot (PHYSICAL → ``passive-physical``, SOCIAL → ``passive-social``, MENTAL →
``passive-mental``) instead of the focused slot.

``CmdClashCommit`` (key ``clash``)
------------------------------------
Commits a technique + optional strain to an active Clash during a DECLARING round.
Routes through the COMBAT backend, wiring the resolved ``Clash.pk`` as
``clash_id`` on the ``ActionRef``.  The dispatcher routes to
``_dispatch_clash_contribution`` which calls ``declare_clash_contribution``.

Syntax: ``clash <opponent> with <technique> [strain=<n>]``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionCategory, CombatActionSlot
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef
    from world.combat.models import CombatParticipant

# Keyword prefix used to parse effort=<level> from command args.
_EFFORT_PREFIX = "effort="
# Standalone keyword that declares the technique as a passive secondary action.
_SECONDARY_KEYWORD = "secondary"
# Keyword prefix used to parse strain=<n> from clash command args.
_STRAIN_PREFIX = "strain="

# Mapping from ActionCategory to the corresponding passive CombatActionSlot.
_SECONDARY_SLOT: dict[str, str] = {
    ActionCategory.PHYSICAL: CombatActionSlot.PASSIVE_PHYSICAL,
    ActionCategory.SOCIAL: CombatActionSlot.PASSIVE_SOCIAL,
    ActionCategory.MENTAL: CombatActionSlot.PASSIVE_MENTAL,
}


class _CombatCommandMixin:
    """Shared helpers for combat telnet commands.

    Provides ``_combat_participant_or_none`` and ``_find_technique_id`` so that
    ``CmdDeclareTechnique`` and ``CmdClashCommit`` can reuse the same lookup logic
    without duplicating it.
    """

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

    def _find_technique_id(self, technique_name: str) -> int:
        """Return the pk of the technique matching *technique_name*.

        Matches case-insensitively against ``Technique.name`` for techniques
        the caller knows (via ``CharacterTechnique``).

        Raises:
            CommandError: If no matching known technique is found.
        """
        from world.magic.models import CharacterTechnique  # noqa: PLC0415

        ct = (
            CharacterTechnique.objects.filter(
                character=self.caller.sheet_data,
                technique__name__iexact=technique_name,
            )
            .select_related("technique")
            .first()
        )
        if ct is None:
            msg = f"You don't know a technique called '{technique_name}'."
            raise CommandError(msg)
        return ct.technique_id


class CmdDeclareTechnique(_CombatCommandMixin, DispatchCommand):
    """Cast a technique — works both in and out of combat.

    Usage:
        cast <technique> [at <target>] [effort=<level>] [secondary]
        declare <technique> [at <target>] [effort=<level>] [secondary]

    Outside combat: casts the technique immediately in the active scene.
    In a DECLARING combat round: declares the technique for this round;
    the round resolves once all participants have declared.

    Optionally focus a specific target with ``at <name>`` and set your effort
    level with ``effort=<level>`` (very_low/low/medium/high/extreme;
    defaults to medium).

    Use ``secondary`` to declare the technique as a passive action in its
    arena slot (the technique's action_category decides the slot).
    """

    key = "cast"
    aliases = ["declare"]
    locks = "cmd:all()"

    # -- Parsed state cached on first call to resolve_action_ref ---------------

    _technique_name: str | None = None
    _target_name: str | None = None
    _effort: str = "medium"
    _secondary: bool = False
    _parsed: bool = False
    _participant: CombatParticipant | None = None

    # --------------------------------------------------------------------------

    def _parse_args(self) -> None:
        """Parse ``self.args`` once; cache technique name, optional target, effort, secondary."""
        if self._parsed:
            return

        import re  # noqa: PLC0415

        from world.fatigue.constants import EffortLevel  # noqa: PLC0415

        raw = (self.args or "").strip()
        if not raw:
            msg = "Usage: cast <technique> [at <target>] [effort=<level>] [secondary]"
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

        # Strip a standalone trailing "secondary" keyword (case-insensitive, whole
        # word). Plain string ops avoid a backtracking-prone regex (ReDoS). Must come
        # after effort= stripping so the remaining raw is clean.
        secondary = False
        stripped = raw.rstrip()
        kw = _SECONDARY_KEYWORD
        if stripped.lower().endswith(kw) and (
            len(stripped) == len(kw) or stripped[-len(kw) - 1].isspace()
        ):
            raw = stripped[: -len(kw)].rstrip()
            secondary = True

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
            msg = "Usage: cast <technique> [at <target>] [effort=<level>] [secondary]"
            raise CommandError(msg)

        self._effort = effort_str
        self._secondary = secondary
        self._parsed = True

    # -- Resolution helpers ----------------------------------------------------

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

        Delegates to the shared mixin helper.  Keeps the zero-argument call
        signature used by the rest of this class.

        Raises:
            CommandError: If no matching known technique is found.
        """
        return self._find_technique_id(self._technique_name or "")

    def _resolve_technique(self) -> Technique:  # type: ignore[name-defined]  # noqa: F821
        """Return the ``Technique`` object named by ``self._technique_name``.

        Uses the same CharacterTechnique lookup as ``_resolve_technique_id`` but
        returns the full object so callers can read ``action_category`` etc.

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
        return ct.technique

    def _resolve_ally_target_id(self, participant: CombatParticipant) -> int | None:
        """Return the pk of the ``CombatParticipant`` named by ``self._target_name``.

        Scoped to the encounter so cross-encounter names cannot be targeted.

        Returns ``None`` when no target name was provided.

        Raises:
            CommandError: If a target name was given but no matching active
                participant was found.
        """
        if not self._target_name:
            return None

        from world.combat.constants import ParticipantStatus  # noqa: PLC0415
        from world.combat.models import CombatParticipant  # noqa: PLC0415

        name = self._target_name
        matches = list(
            CombatParticipant.objects.filter(
                encounter=participant.encounter,
                status=ParticipantStatus.ACTIVE,
                character_sheet__character__db_key__iexact=name,
            )
        )
        if not matches:
            msg = f"No active ally named '{name}' in this encounter."
            raise CommandError(msg)
        if len(matches) > 1:
            msg = f"More than one ally named '{name}' — be more specific."
            raise CommandError(msg)
        return matches[0].pk

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

        When ``secondary`` was parsed, the action_slot is derived from the
        technique's ``action_category`` and included in the ref so
        ``round_declaration`` routes to the correct passive slot.
        """
        from actions.constants import ActionBackend  # noqa: PLC0415
        from actions.types import ActionRef  # noqa: PLC0415

        self._parse_args()
        technique_id = self._resolve_technique_id()

        action_slot = None
        if self._secondary:
            technique = self._resolve_technique()
            action_slot = _SECONDARY_SLOT.get(technique.action_category)

        return ActionRef(
            backend=ActionBackend.SCENE_ADAPTIVE,
            registry_key="cast_technique",
            technique_id=technique_id,
            action_slot=action_slot,
        )

    def resolve_action_args(self) -> dict[str, Any]:
        """Return dispatch kwargs; routes target resolution by context.

        Always includes ``effort_level``.  If ``at <target>`` was given in a
        combat context the technique's authored target relationship decides
        the kwarg:
        - ``ENEMY`` → ``focused_opponent_target_id`` (CombatOpponent pk).
        - ``ALLY``/``SELF`` → ``focused_ally_target_id`` (CombatParticipant pk).

        In a non-combat context ``at <target>`` resolves as
        ``target_persona_id`` (Persona pk).

        When ``secondary`` was parsed, ``action_slot`` is forwarded so
        ``CastTechniqueAction.round_declaration`` routes to the passive slot.
        """
        from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415
        from world.magic.services.targeting import derive_target_relationship  # noqa: PLC0415

        self._parse_args()
        kwargs: dict[str, Any] = {"effort_level": self._effort}

        if self._secondary:
            technique = self._resolve_technique()
            slot = _SECONDARY_SLOT.get(technique.action_category)
            if slot is not None:
                kwargs["action_slot"] = slot

        if not self._target_name:
            return kwargs

        # Check whether we're in a DECLARING combat round to decide how to
        # resolve the target name. Cache the participant for later helpers.
        participant = self._combat_participant_or_none()
        if participant is not None:
            self._participant = participant
            # Use the technique's authored relationship to route target resolution.
            technique = self._resolve_technique()
            relationship = derive_target_relationship(technique)
            if relationship == ConditionTargetKind.ENEMY:
                opp_id = self._resolve_opponent_target_id()
                if opp_id is not None:
                    kwargs["focused_opponent_target_id"] = opp_id
            else:
                # ALLY or SELF: resolve as a CombatParticipant in this encounter.
                ally_id = self._resolve_ally_target_id(participant)
                if ally_id is not None:
                    kwargs["focused_ally_target_id"] = ally_id
        else:
            persona_id = self._resolve_target_persona_id()
            if persona_id is not None:
                kwargs["target_persona_id"] = persona_id

        return kwargs


class CmdClashCommit(_CombatCommandMixin, DispatchCommand):
    """Commit a technique to an active Clash during a DECLARING combat round.

    Usage:
        clash <opponent> with <technique> [strain=<n>]

    Identifies the active Clash against the named NPC opponent and declares a
    ClashContributionDeclaration via the COMBAT backend dispatcher.  The round
    resolves when all participants have declared; the clash post-pass then drives
    ``run_clash_round`` and writes ``ClashContribution`` audit rows.

    ``strain=<n>`` commits extra anima beyond the technique's base cost (default 0).
    """

    key = "clash"
    locks = "cmd:all()"

    # -- Parsed state -----------------------------------------------------------

    _opponent_name: str | None = None
    _technique_name: str | None = None
    _strain: int = 0
    _parsed: bool = False

    # ---------------------------------------------------------------------------

    def _parse_args(self) -> None:
        """Parse ``self.args`` once; cache opponent, technique, and strain."""
        if self._parsed:
            return

        import re  # noqa: PLC0415

        raw = (self.args or "").strip()
        if not raw:
            msg = "Usage: clash <opponent> with <technique> [strain=<n>]"
            raise CommandError(msg)

        # Strip off strain=<n> suffix (case-insensitive).
        strain = 0
        if _STRAIN_PREFIX in raw.lower():
            parts = re.split(re.escape(_STRAIN_PREFIX), raw, flags=re.IGNORECASE)
            raw = parts[0].strip()
            strain_str = parts[1].strip()
            if not strain_str.isdigit():
                msg = f"Invalid strain value '{strain_str}' — must be a non-negative integer."
                raise CommandError(msg)
            strain = int(strain_str)

        # Split on " with " (case-insensitive) to separate opponent from technique.
        with_index = raw.lower().find(" with ")
        if with_index == -1:
            msg = "Usage: clash <opponent> with <technique> [strain=<n>]"
            raise CommandError(msg)

        self._opponent_name = raw[:with_index].strip()
        self._technique_name = raw[with_index + len(" with ") :].strip()

        if not self._opponent_name or not self._technique_name:
            msg = "Usage: clash <opponent> with <technique> [strain=<n>]"
            raise CommandError(msg)

        self._strain = strain
        self._parsed = True

    def _resolve_clash(self, participant: CombatParticipant) -> Any:
        """Return the active Clash for this participant's encounter against the named opponent.

        Raises:
            CommandError: If no active Clash matches or the name is ambiguous.
        """
        from world.combat.constants import ClashStatus  # noqa: PLC0415
        from world.combat.models import Clash  # noqa: PLC0415

        name = self._opponent_name or ""
        matches = list(
            Clash.objects.filter(
                encounter=participant.encounter,
                status=ClashStatus.ACTIVE,
                npc_opponent__name__iexact=name,
            ).select_related("npc_opponent")
        )
        if not matches:
            msg = f"No active Clash against '{name}' in this encounter."
            raise CommandError(msg)
        if len(matches) > 1:
            msg = f"More than one active Clash against '{name}' — be more specific."
            raise CommandError(msg)
        return matches[0]

    # -- DispatchCommand interface ---------------------------------------------

    def resolve_action_ref(self) -> ActionRef:
        """Build a COMBAT ``ActionRef`` carrying the resolved Clash pk.

        Locates the caller's active DECLARING participant, then finds the
        active Clash against the named opponent.  Raises ``CommandError`` when
        the caller is not in a DECLARING round or no matching Clash is found.
        """
        from actions.constants import ActionBackend  # noqa: PLC0415
        from actions.types import ActionRef  # noqa: PLC0415

        self._parse_args()

        participant = self._combat_participant_or_none()
        if participant is None:
            msg = "You are not in an active combat round."
            raise CommandError(msg)

        clash = self._resolve_clash(participant)

        # ClashActionSlot.FOCUSED.value == "FOCUSED" (TextChoices first element).
        # Pass the string literal directly to avoid a ty false-positive on
        # TextChoices value extraction (same pattern used in player_interface.py).
        return ActionRef(
            backend=ActionBackend.COMBAT,
            clash_id=clash.pk,
            clash_action_slot="FOCUSED",
        )

    def resolve_action_args(self) -> dict[str, Any]:
        """Return ``technique_id`` and ``strain_commitment`` for the dispatcher."""
        self._parse_args()
        technique_id = self._find_technique_id(self._technique_name or "")
        return {
            "technique_id": technique_id,
            "strain_commitment": self._strain,
        }
