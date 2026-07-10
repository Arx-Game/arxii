"""Combat maneuver telnet command — the ``combat <subverb>`` namespace (#1453, #1452).

A single command routes the non-cast/non-clash combat verbs (flee, cover,
interpose, succor, join, leave, ready, combo, revert, yield) through the shared
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
    "succor": "combat_succor",
    "use": "combat_use",
    "join": "combat_join",
    "leave": "combat_leave",
    "ready": "combat_ready",
    "combo": "combat_combo",
    "revert": "combat_revert",
    "yield": "yield",
    "rally": "combat_rally",
    "demoralize": "combat_demoralize",
    "taunt": "combat_taunt",
    "parley": "combat_parley",
}

# subverbs that take a single name argument.
_ALLY_SUBVERBS = {"cover", "interpose", "succor", "rally"}
_OPPONENT_SUBVERBS = {"demoralize", "taunt", "parley"}


class CmdCombat(_CombatCommandMixin, DispatchCommand):
    """Take a combat action other than casting or clashing.

    Usage:
        combat                      — show your combat status + available actions
        combat flee                 — declare a desperate flee this round
        combat cover <ally>         — cover an ally's escape
        combat interpose [ally]     — guard an ally (or any ally) from harm
        combat succor <ally>        — shelter an ally from environmental hazards
        combat use <item> [on <target>] — use a held on-use item this round
        combat rally <ally>         — inspire an ally, bolstering their next action
        combat demoralize <opp>     — break an opponent's nerve (morale damage)
        combat taunt <opp>          — draw an NPC's aggro toward you
        combat parley <opp>          — talk a wavering foe down mid-fight
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

    def resolve_action_args(self) -> dict[str, Any]:  # noqa: PLR0911
        """Resolve name arguments (ally / opponent / combo) into dispatch kwargs."""
        if self._subverb == "cover":  # noqa: STRING_LITERAL
            return {"ally_participant_id": self._resolve_ally_pk(self._require_rest("an ally"))}
        if self._subverb == "interpose":  # noqa: STRING_LITERAL
            ally = self._resolve_ally_pk(self._rest) if self._rest else None
            return {"ally_participant_id": ally}
        if self._subverb == "succor":  # noqa: STRING_LITERAL
            return {"ally_participant_id": self._resolve_ally_pk(self._require_rest("an ally"))}
        if self._subverb == "rally":  # noqa: STRING_LITERAL
            return {"ally_participant_id": self._resolve_ally_pk(self._require_rest("an ally"))}
        if self._subverb in _OPPONENT_SUBVERBS:
            return {"opponent_id": self._resolve_opponent_pk(self._require_rest("an opponent"))}
        if self._subverb == "combo":  # noqa: STRING_LITERAL
            return {"combo_id": self._resolve_combo_pk(self._require_rest("a combo name"))}
        if self._subverb == "use":  # noqa: STRING_LITERAL
            return self._resolve_use_item_args(self._require_rest("an item"))
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

    def _resolve_opponent_pk(self, name: str) -> int:
        """Return the pk of the active opponent named *name* in the caller's encounter."""
        from world.combat.constants import OpponentStatus  # noqa: PLC0415
        from world.combat.models import CombatOpponent  # noqa: PLC0415

        participant = self._combat_participant_or_none()
        if participant is None:
            msg = "You are not in an active combat round."
            raise CommandError(msg)
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

    def _resolve_use_item_args(self, text: str) -> dict[str, Any]:
        """Parse ``<item> [on <target>]`` (#2120, mirrors ``CmdUse``'s ``on`` grammar).

        The item name is resolved to a held ``ItemInstance`` by
        ``UseItemManeuverAction`` itself (kwarg ``item_name``); this only
        splits the text and, when a target clause is present, resolves it to
        an ally or opponent kwarg.
        """
        item_text, _, target_text = text.partition(" on ")
        item_text = item_text.strip()
        if not item_text:
            msg = "Use what?"
            raise CommandError(msg)
        kwargs: dict[str, Any] = {"item_name": item_text}
        target_text = target_text.strip()
        if target_text:
            kwargs.update(self._resolve_use_item_target(target_text))
        return kwargs

    def _resolve_use_item_target(self, name: str) -> dict[str, Any]:
        """Resolve a use-item target name to an ally or opponent kwarg (#2120).

        Tries an active ally first, then an active opponent -- USE_ITEM's
        target can be either (heal an ally / throw at a foe), unlike the
        ally-only or opponent-only subverbs above.
        """
        from world.combat.constants import OpponentStatus, ParticipantStatus  # noqa: PLC0415
        from world.combat.models import CombatOpponent, CombatParticipant  # noqa: PLC0415

        participant = self._combat_participant_or_none()
        if participant is None:
            msg = "You are not in an active combat round."
            raise CommandError(msg)
        ally_matches = list(
            CombatParticipant.objects.filter(
                encounter=participant.encounter,
                status=ParticipantStatus.ACTIVE,
                character_sheet__character__db_key__iexact=name,
            )
        )
        opponent_matches = list(
            CombatOpponent.objects.filter(
                encounter=participant.encounter,
                status=OpponentStatus.ACTIVE,
                name__iexact=name,
            )
        )
        total = len(ally_matches) + len(opponent_matches)
        if total == 0:
            msg = f"No active ally or opponent named '{name}' in this encounter."
            raise CommandError(msg)
        if total > 1:
            msg = f"More than one target named '{name}' — be more specific."
            raise CommandError(msg)
        if ally_matches:
            return {"ally_participant_id": ally_matches[0].pk}
        return {"opponent_id": opponent_matches[0].pk}

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
        character = self.caller.puppet if hasattr(self.caller, "puppet") else self.caller
        lines: list[str] = []
        lines.extend(self._anima_lines(character))
        lines.extend(self._soulfray_lines(character))
        if participant is not None:
            lines.extend(self._fury_and_berserk_lines(character, action))
        return lines

    @staticmethod
    def _anima_lines(character: Any) -> list[str]:
        """Current/maximum anima, or nothing when there's no anima row yet."""
        try:
            anima = character.anima
        except (AttributeError, ObjectDoesNotExist):
            return []  # No anima row yet — omit rather than mislead with 0/0.
        return [f"Anima: {anima.current}/{anima.maximum}"]

    @staticmethod
    def _soulfray_lines(character: Any) -> list[str]:
        """Soulfray stage (with death-risk marker), or nothing when none."""
        from world.magic.services.soulfray import get_soulfray_warning  # noqa: PLC0415

        warning = get_soulfray_warning(character)
        if warning is None:
            return []
        risk = " — |rdeath risk|n" if warning.has_death_risk else ""
        return [f"Soulfray: {warning.stage_name}{risk}"]

    def _fury_and_berserk_lines(self, character: Any, action: Any) -> list[str]:
        """Fury-commitment and Berserk lines for an in-encounter participant."""
        berserk = self._berserk_instance(character)
        lines: list[str] = []
        if action is not None and action.fury_commitment_id:
            lines.append(self._fury_line(action, berserk))
        if berserk is not None:
            lines.append(self._berserk_line(berserk))
        return lines

    @staticmethod
    def _fury_line(action: Any, berserk: Any) -> str:
        """One line describing the committed fury and whether control is held."""
        control = "lost" if berserk is not None else "retained"
        anchor_name = "unknown"
        if action.fury_anchor_id and action.fury_anchor is not None:
            anchor_char = action.fury_anchor.character
            if anchor_char is not None:
                anchor_name = anchor_char.db_key
        return (
            f"Fury: committed (depth {action.fury_commitment.depth}, "
            f"anchored to {anchor_name}) — control {control}"
        )

    @staticmethod
    def _berserk_line(berserk: Any) -> str:
        """One line describing the active Berserk condition and rounds left."""
        rounds = ""
        if berserk.rounds_remaining is not None:
            unit = "round" if berserk.rounds_remaining == 1 else "rounds"
            rounds = f" ({berserk.rounds_remaining} {unit} left)"
        return f"Berserk: active{rounds}"

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
            "flee, cover <ally>, interpose [ally], succor <ally>, use <item> [on <target>], "
            "rally <ally>, demoralize <opp>, taunt <opp>, parley <opp>, join, leave, ready, "
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
