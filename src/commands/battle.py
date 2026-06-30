"""Telnet battle namespace command (#1592).

One ``battle`` command routes a leading subverb to the battle lifecycle actions.

Player subverbs:
    battle              — show caller's current battle status
    battle declare strike <unit>
    battle declare support <char>

GM subverbs:
    battle round        — begin the next round (DECLARING)
    battle resolve      — resolve the current round
    battle conclude     — force-conclude the battle

No business logic lives here: parse, resolve model instances, call Action.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionResult
    from world.battles.models import BattleParticipant, BattleUnit


class CmdBattle(ArxCommand):
    """Manage your participation in a large-scale battle.

    Syntax (player):
        battle
        battle declare strike <unit>
        battle declare support <ally>

    Syntax (GM / staff):
        battle round
        battle resolve
        battle conclude

    Bare ``battle`` shows your current battle status. Supply a unit name for
    ``strike`` (matched within the active battle) or a character name for
    ``support``.
    """

    key = "battle"
    locks = "cmd:all()"
    action = None  # routes to multiple actions

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    # ------------------------------------------------------------------
    # Dispatch

    def _dispatch(self) -> None:
        args = (self.args or "").strip()
        if not args:
            self._status()
            return
        tokens: list[str] = list(args.split())
        first = tokens[0].lower()
        rest = tokens[1:]

        if first == "declare":  # noqa: STRING_LITERAL
            self._declare(rest)
        elif first == "round":  # noqa: STRING_LITERAL
            self._begin_round()
        elif first == "resolve":  # noqa: STRING_LITERAL
            self._resolve_round()
        elif first == "conclude":  # noqa: STRING_LITERAL
            self._conclude()
        else:
            msg = (
                "Usage: battle [declare strike <unit>|declare support <char>"
                "|round|resolve|conclude]"
            )
            raise CommandError(msg)

    # ------------------------------------------------------------------
    # Resolution helpers

    def _actor_sheet(self) -> object:
        sheet = getattr(self.caller, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)
        return sheet

    def _resolve_participant(self) -> BattleParticipant:
        """Return the caller's active BattleParticipant or raise CommandError."""
        from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
        from world.battles.models import BattleParticipant  # noqa: PLC0415

        sheet = self._actor_sheet()
        participant = (
            BattleParticipant.objects.filter(
                character_sheet=sheet,
                status=BattleParticipantStatus.ACTIVE,
                battle__scene__is_active=True,
            )
            .select_related("battle", "side")
            .order_by("-battle__created_at")
            .first()
        )
        if participant is None:
            msg = "You are not an active participant in any battle."
            raise CommandError(msg)
        return participant

    def _resolve_unit(self, participant: BattleParticipant, name: str) -> BattleUnit:
        """Resolve a BattleUnit by name within the participant's battle."""
        from world.battles.constants import BattleUnitStatus  # noqa: PLC0415
        from world.battles.models import BattleUnit  # noqa: PLC0415

        unit = BattleUnit.objects.filter(
            battle=participant.battle,
            name__iexact=name,
            status=BattleUnitStatus.ACTIVE,
        ).first()
        if unit is None:
            msg = f"No active unit named '{name}' in this battle."
            raise CommandError(msg)
        return unit

    def _resolve_ally(self, participant: BattleParticipant, char_name: str) -> BattleParticipant:
        """Resolve an allied BattleParticipant by character name."""
        from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
        from world.battles.models import BattleParticipant  # noqa: PLC0415

        ally = BattleParticipant.objects.filter(
            battle=participant.battle,
            status=BattleParticipantStatus.ACTIVE,
            character_sheet__character__db_key__iexact=char_name,
        ).first()
        if ally is None:
            msg = f"No active participant named '{char_name}' in this battle."
            raise CommandError(msg)
        return ally

    def _send(self, result: ActionResult) -> None:
        if result.message:
            self.msg(result.message)

    # ------------------------------------------------------------------
    # Subverb handlers

    def _status(self) -> None:
        from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
        from world.battles.models import BattleParticipant  # noqa: PLC0415

        sheet = self._actor_sheet()
        participant = (
            BattleParticipant.objects.filter(
                character_sheet=sheet,
                status=BattleParticipantStatus.ACTIVE,
                battle__scene__is_active=True,
            )
            .select_related("battle", "side", "place")
            .order_by("-battle__created_at")
            .first()
        )
        if participant is None:
            self.msg("You are not currently enlisted in any active battle.")
            return

        battle = participant.battle
        current_round = battle.current_round
        lines = [
            f"Battle: {battle.name}",
            f"Side: {participant.side.get_role_display()}",
            f"VP: {participant.side.victory_points} / {participant.side.victory_threshold}",
        ]
        if participant.place:
            lines.append(f"Front: {participant.place.name}")
        if current_round is not None:
            lines.append(
                f"Round {current_round.round_number}: {current_round.get_status_display()}"
            )
        else:
            lines.append("No active round.")
        self.msg("\n".join(lines))

    def _declare(self, rest: list[str]) -> None:
        from actions.definitions.battles import DeclareBattleActionAction  # noqa: PLC0415
        from world.battles.constants import BattleActionKind  # noqa: PLC0415

        if not rest:
            msg = "Usage: battle declare strike <unit> | battle declare support <ally>"
            raise CommandError(msg)

        kind = rest[0].lower()
        name = " ".join(rest[1:]).strip()

        if kind == "strike":  # noqa: STRING_LITERAL
            if not name:
                msg = "Declare strike against which unit? (battle declare strike <unit>)"
                raise CommandError(msg)
            participant = self._resolve_participant()
            unit = self._resolve_unit(participant, name)
            result = DeclareBattleActionAction().run(
                self.caller,
                action_kind=BattleActionKind.STRIKE,
                target_unit=unit,
            )
        elif kind == "support":  # noqa: STRING_LITERAL
            if not name:
                msg = "Support which ally? (battle declare support <ally>)"
                raise CommandError(msg)
            participant = self._resolve_participant()
            ally = self._resolve_ally(participant, name)
            result = DeclareBattleActionAction().run(
                self.caller,
                action_kind=BattleActionKind.SUPPORT,
                target_ally=ally,
            )
        else:
            msg = "Unknown declare subverb. Use 'strike' or 'support'."
            raise CommandError(msg)

        self._send(result)

    def _begin_round(self) -> None:
        from actions.definitions.battles import BeginBattleRoundAction  # noqa: PLC0415

        result = BeginBattleRoundAction().run(self.caller)
        self._send(result)

    def _resolve_round(self) -> None:
        from actions.definitions.battles import ResolveBattleRoundAction  # noqa: PLC0415

        result = ResolveBattleRoundAction().run(self.caller)
        self._send(result)

    def _conclude(self) -> None:
        from actions.definitions.battles import ConcludeBattleAction  # noqa: PLC0415

        result = ConcludeBattleAction().run(self.caller)
        self._send(result)
