"""Combat maneuver telnet command — the ``combat <subverb>`` namespace (#1453, #1452).

A single command routes the non-cast/non-clash combat verbs (flee, cover,
interpose, join, leave, ready, combo, revert, yield) through the shared
``dispatch_player_action`` seam — the same path the web uses. The verbs live
under the ``combat`` namespace rather than as bare top-level keys because broad
one-word keys (``join``/``leave``/``ready``/``cover``/``revert``) collide with
room exits, channels, and aliases. Mirrors ``CmdRitual`` (subverb routing) and
``CmdSheet`` (the section-hub pattern).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.constants import ActionBackend
from commands.combat import _CombatCommandMixin
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

# subverb -> registry action key. ``yield`` reuses the existing YieldAction.
_SUBVERBS: dict[str, str] = {
    "flee": "combat_flee",
    "cover": "combat_cover",
    "interpose": "combat_interpose",
    "join": "combat_join",
    "leave": "combat_leave",
    "ready": "combat_ready",
    "combo": "combat_combo",
    "revert": "combat_revert",
    "yield": "yield",
}

# subverbs that take a single name argument.
_ALLY_SUBVERBS = {"cover", "interpose"}


class CmdCombat(_CombatCommandMixin, DispatchCommand):
    """Take a combat action other than casting or clashing.

    Usage:
        combat                      — show your combat status + available actions
        combat flee                 — declare a desperate flee this round
        combat cover <ally>         — cover an ally's escape
        combat interpose [ally]     — guard an ally (or any ally) from harm
        combat join                 — join the fight in your room
        combat leave                — leave an open encounter between rounds
        combat ready                — toggle your declared action as ready
        combat combo <name>         — chain your declared action into a combo
        combat revert               — undo a combo upgrade
        combat yield                — concede a duel
    """

    key = "combat"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``combat`` shows the status hub."""
        raw = (self.args or "").strip()
        if not raw:
            self._show_status_hub()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(_SUBVERBS)
            self.msg(f"Unknown combat action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve name arguments (ally / combo) into dispatch kwargs."""
        if self._subverb == "cover":  # noqa: STRING_LITERAL
            return {"ally_participant_id": self._resolve_ally_pk(self._require_rest("an ally"))}
        if self._subverb == "interpose":  # noqa: STRING_LITERAL
            ally = self._resolve_ally_pk(self._rest) if self._rest else None
            return {"ally_participant_id": ally}
        if self._subverb == "combo":  # noqa: STRING_LITERAL
            return {"combo_id": self._resolve_combo_pk(self._require_rest("a combo name"))}
        return {}

    # -- helpers ---------------------------------------------------------------

    def _require_rest(self, what: str) -> str:
        if not self._rest:
            msg = f"Usage: combat {self._subverb} <{what}>."
            raise CommandError(msg)
        return self._rest

    def _resolve_ally_pk(self, name: str) -> int:
        """Return the pk of the active ally named *name* in the caller's encounter."""
        from world.combat.constants import ParticipantStatus  # noqa: PLC0415
        from world.combat.models import CombatParticipant  # noqa: PLC0415

        participant = self._combat_participant_or_none()
        if participant is None:
            msg = "You are not in an active combat round."
            raise CommandError(msg)
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

    def _resolve_combo_pk(self, name: str) -> int:
        from world.combat.models import ComboDefinition  # noqa: PLC0415

        combo = ComboDefinition.objects.filter(name__iexact=name).first()
        if combo is None:
            msg = f"No combo named '{name}'."
            raise CommandError(msg)
        return combo.pk

    def _render_resource_state(self, participant: Any, action: Any) -> list[str]:
        """Anima + soulfray (always, if present) + fury/Berserk (active round only).

        Read-only over existing services — no mechanics. ``participant`` is the
        caller's CombatParticipant or None; ``action`` is this round's
        CombatRoundAction (or None). Fury/Berserk are suppressed when
        ``participant`` is None (outside an encounter).
        """
        from world.magic.services.soulfray import get_soulfray_warning  # noqa: PLC0415

        lines: list[str] = []
        character = self.caller.puppet if hasattr(self.caller, "puppet") else self.caller
        try:
            anima = character.anima
            lines.append(f"Anima: {anima.current}/{anima.maximum}")
        except (AttributeError, ObjectDoesNotExist):
            pass  # No anima row yet — omit rather than mislead with 0/0.

        warning = get_soulfray_warning(character)
        if warning is not None:
            risk = " — |rdeath risk|n" if warning.has_death_risk else ""
            lines.append(f"Soulfray: {warning.stage_name}{risk}")

        if participant is not None:
            berserk = self._berserk_instance(character)
            control = "lost" if berserk is not None else "retained"
            if action is not None and action.fury_commitment_id:
                anchor_name = "unknown"
                if action.fury_anchor_id and action.fury_anchor is not None:
                    anchor_char = action.fury_anchor.character
                    if anchor_char is not None:
                        anchor_name = anchor_char.db_key
                lines.append(
                    f"Fury: committed (depth {action.fury_commitment.depth}, "
                    f"anchored to {anchor_name}) — control {control}"
                )
            if berserk is not None:
                rounds = ""
                if berserk.rounds_remaining is not None:
                    unit = "round" if berserk.rounds_remaining == 1 else "rounds"
                    rounds = f" ({berserk.rounds_remaining} {unit} left)"
                lines.append(f"Berserk: active{rounds}")
        return lines

    def _berserk_instance(self, character: Any) -> Any:
        """The active Berserk ConditionInstance on *character*, or None."""
        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        return ConditionInstance.objects.filter(
            target=character,
            condition__name="Berserk",
        ).first()

    def _show_status_hub(self) -> None:
        """Print resource/risk state + the declared action + available subverbs."""
        lines = [
            "|wCombat actions|n: "
            "flee, cover <ally>, interpose [ally], join, leave, ready, "
            "combo <name>, revert, yield"
        ]
        participant = self._combat_participant_or_none()
        if participant is None:
            lines.extend(self._render_resource_state(participant, None))
            lines.append("You are not currently declaring in combat.")
        else:
            from world.combat.models import CombatRoundAction  # noqa: PLC0415

            action = (
                CombatRoundAction.objects.select_related(
                    "fury_commitment", "fury_anchor__character"
                )
                .filter(
                    participant=participant,
                    round_number=participant.encounter.round_number,
                )
                .first()
            )
            lines.extend(self._render_resource_state(participant, action))
            if action is None:
                lines.append("You have not declared an action this round.")
            else:
                ready = "ready" if action.is_ready else "not ready"
                maneuver = action.maneuver or "action"
                lines.append(f"Declared: {maneuver} ({ready}).")
        self.msg("\n".join(lines))
