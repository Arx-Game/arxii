"""Telnet battle namespace command (#1592).

One ``battle`` command routes a leading subverb to the battle lifecycle actions.

Player subverbs:
    battle              — show caller's current battle status
    battle declare strike <unit> with <technique>
    battle declare strike side with <technique>
    battle declare strike place <name> with <technique>
    battle declare support <char> with <technique>
    battle declare rescue <ally> with <technique>
    battle declare rout <unit> with <technique>
    battle declare rally <unit> with <technique>
    battle declare repel place <name> with <technique>
    battle declare hold place <name> with <technique>
    battle declare breach place <name> fortification <kind> with <technique>
    battle declare fortify place <name> fortification <kind> with <technique>
    battle declare set_environment with <technique>
    battle declare set_environment place <name> with <technique>
    battle declare move <place> with <technique>
    battle declare move <unit> to <place> with <technique>
    battle declare move withdraw with <technique>
    battle declare reposition <place> <dx> <dy> with <technique>
    battle duel <front> vs <boss name>

GM subverbs:
    battle round        — begin the next round (DECLARING)
    battle resolve      — resolve the current round
    battle conclude     — force-conclude the battle

GM staging subverbs (#2010 — turn a catalog pick into a live Battle):
    battle create <name> [risk=<level>] [map=<blueprint>]
    battle stage <blueprint> [replace]
    battle spawn <template> [count=N] [at <front>] side=<role>
    battle enlist <character> = <side>[, <front>]
    battle maps [<term>]
    battle units [<term>]

No business logic lives here: parse, resolve model instances, call Action.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.parsing import parse_kv_and_flags
from commands.utils.gm_resolution import (
    resolve_account_or_none,
    resolve_character_sheet_in_room,
    resolve_model_by_pk_or_name,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from actions.types import ActionResult
    from world.battles.models import (
        Battle,
        BattleMapBlueprint,
        BattleParticipant,
        BattlePlace,
        BattleSide,
        BattleUnit,
        BattleUnitTemplate,
    )

_PLACE_PREFIX = "place "
_AT_MARKER = "at"  # noqa: STRING_LITERAL


def _split_leading_positional(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split *tokens* at the first ``key=value`` token (#2010).

    Returns (positional tokens before the first key=value token, the
    remaining tokens from that point on) — used to separate a free-text
    leading name/label (which may contain spaces) from a trailing
    ``key=value`` clause, e.g. ``battle create <name> [risk=<level>]``.
    """
    for index, token in enumerate(tokens):
        if "=" in token and not token.startswith("="):
            return tokens[:index], tokens[index:]
    return tokens, []


class CmdBattle(ArxCommand):
    """Manage your participation in a large-scale battle.

    Syntax (player):
        battle
        battle declare strike <unit> with <technique>
        battle declare strike side with <technique>
        battle declare strike place <name> with <technique>
        battle declare support <ally> with <technique>
        battle declare rescue <ally> with <technique>
        battle declare rout <unit> with <technique>
        battle declare rally <unit> with <technique>
        battle declare repel place <name> with <technique>
        battle declare hold place <name> with <technique>
        battle declare breach place <name> fortification <kind> with <technique>
        battle declare fortify place <name> fortification <kind> with <technique>
        battle declare set_environment with <technique>
        battle declare set_environment place <name> with <technique>
        battle declare move <place> with <technique>
        battle declare move <unit> to <place> with <technique>
        battle declare move withdraw with <technique>
        battle declare reposition <place> <dx> <dy> with <technique>
        battle duel <front> vs <boss name>

    Syntax (GM / staff):
        battle round
        battle resolve
        battle conclude

    Syntax (GM staging, #2010):
        battle create <name> [risk=<level>] [map=<blueprint>]
        battle stage <blueprint> [replace]
        battle spawn <template> [count=N] [at <front>] side=<role>
        battle enlist <character> = <side>[, <front>]
        battle maps [<term>]
        battle units [<term>]

    Bare ``battle`` shows your current battle status. Supply a unit name for
    ``strike`` (matched within the active battle) or a character name for
    ``support``/``rescue``, plus the technique you know to cast with
    ``with <technique>``. ``rescue`` clears a Surrounded ally's peril instead
    of awarding victory points. ``strike side`` declares an army-wide SIDE-scope
    strike against the opposing side (command-hierarchy fan-out across every
    active enemy unit) instead of a single unit — requires an engaged SUPREME
    command_tier on your own side's covenant. ``strike place <name>`` is the
    same fan-out narrowed to one front (``BattlePlace``) — requires an engaged
    SUBORDINATE or SUPREME command_tier. ``rout`` targets an enemy unit
    (ACTIVE only) to push it toward breaking. ``rally`` targets a unit on
    *your own* side, including one that's already ROUTED — that's the whole
    point of rallying it. ``repel``/``hold`` are PLACE-scope only, aimed at a
    front (``BattlePlace``) rather than a single unit or an entire side.
    ``breach``/``fortify`` target a specific ``Fortification`` at a front by
    kind (``wall``/``gate``/``battlement``) — ``place <name> fortification
    <kind>`` — since a front may carry more than one structure and a
    Fortification has no name of its own.
    ``set_environment`` casts battlefield weather (#1715) — the technique
    itself carries the weather type, so no separate weather argument is
    needed; with no target it casts at BATTLE scope (whole-battle-wide,
    requires an engaged SUPREME command_tier), or ``place <name>`` narrows it
    to a PLACE-scope local exception at that front only.
    ``duel <front> vs <boss name>`` opens a lethal Champion duel bound to that
    front — requires an engaged Champion role for your side's covenant.
    ``move <place>`` repositions yourself to a different front; ``move <unit> to
    <place>`` is a commander's order (requires an engaged SUBORDINATE or SUPREME
    command_tier, same as ``repel``/``hold``); ``move withdraw`` leaves the battle
    entirely. ``reposition <place> <dx> <dy>`` moves a vehicle you command by the
    given delta, clamped to its SPEED capability (#1714).

    The staging subverbs (#2010) turn a JUNIOR-GM catalog pick into a live
    Battle: ``create`` makes a new Battle (optionally staging a named
    ``BattleMapBlueprint`` at creation time via ``map=``) and binds its Scene
    to your current room (#2010 Task 4), so ``battle round``/``resolve``/
    ``conclude`` (which resolve "the active battle in this room") can act on
    it right away; ``stage`` clones a named blueprint's fronts onto your
    current staged battle (``replace`` tears down and re-stages an existing
    map, when safe to do so); ``spawn`` mints one or more
    ``BattleUnitTemplate`` copies onto a side, optionally at a named front;
    ``enlist`` adds a player character to a side (and optionally a front).
    ``maps``/``units`` browse the two catalogs by name (both search both
    catalogs — a term matching only one shows only that section). ``create``/
    ``stage``/``spawn``/``enlist``/``maps``/``units`` act on **your own
    most-recently-created, unresolved battle** — the one ``create`` just made
    you the GM of — addressed by id, not by room.
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

        # Dispatch tables keyed by subverb, mirroring _declare's dict pattern
        # below -- keeps this method's cyclomatic complexity flat as new
        # subverbs are added (#2010 added six).
        arg_handlers: dict[str, Callable[[list[str]], None]] = {
            "declare": self._declare,
            "duel": self._challenge_duel,
            "create": self._create_battle,
            "stage": self._stage_map,
            "spawn": self._spawn_units,
            "enlist": self._enlist_participant,
            "maps": self._browse_catalog,
            "units": self._browse_catalog,
        }
        no_arg_handlers: dict[str, Callable[[], None]] = {
            "round": self._begin_round,
            "resolve": self._resolve_round,
            "conclude": self._conclude,
        }

        if first in arg_handlers:
            arg_handlers[first](rest)
            return
        if first in no_arg_handlers:
            no_arg_handlers[first]()
            return

        msg = (
            "Usage: battle [declare strike <unit>|declare support <char>"
            "|declare rescue <ally>|duel <front> vs <boss name>|round|resolve|conclude"
            "|create <name>|stage <blueprint>|spawn <template>|enlist <char> = <side>"
            "|maps [<term>]|units [<term>]]"
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

    def _resolve_own_unit(self, participant: BattleParticipant, name: str) -> BattleUnit:
        """Resolve a BattleUnit by name within the participant's own side (RALLY, #1712).

        Unlike ``_resolve_unit`` (STRIKE/ROUT — ACTIVE only, any side), this also
        matches ROUTED units — rallying a unit that's already broken is the point.
        """
        from world.battles.constants import BattleUnitStatus  # noqa: PLC0415
        from world.battles.models import BattleUnit  # noqa: PLC0415

        unit = BattleUnit.objects.filter(
            battle=participant.battle,
            side=participant.side,
            name__iexact=name,
            status__in=(BattleUnitStatus.ACTIVE, BattleUnitStatus.ROUTED),
        ).first()
        if unit is None:
            msg = f"No active or routed unit named '{name}' on your side in this battle."
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

    def _resolve_technique(self, participant: BattleParticipant, name: str) -> object:
        """Resolve a known Technique by name for the participant's character."""
        from world.magic.models import CharacterTechnique  # noqa: PLC0415

        link = (
            CharacterTechnique.objects.filter(
                character=participant.character_sheet,
                technique__name__iexact=name,
            )
            .select_related("technique")
            .first()
        )
        if link is None:
            msg = f"You don't know a technique named '{name}'."
            raise CommandError(msg)
        return link.technique

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
        if battle.is_paused:
            lines.append("Status: PAUSED (a participant recently disconnected)")
        self.msg("\n".join(lines))

    def _declare(self, rest: list[str]) -> None:
        from world.battles.constants import BattleActionKind  # noqa: PLC0415

        if not rest:
            msg = (
                "Usage: battle declare strike <unit> with <technique>"
                " | battle declare support <ally> with <technique>"
                " | battle declare rescue <ally> with <technique>"
                " | battle declare rout <unit> with <technique>"
                " | battle declare rally <unit> with <technique>"
                " | battle declare repel place <name> with <technique>"
                " | battle declare hold place <name> with <technique>"
                " | battle declare breach place <name> fortification <kind> with <technique>"
                " | battle declare fortify place <name> fortification <kind> with <technique>"
                " | battle declare set_environment [place <name>] with <technique>"
                " | battle declare move <place> with <technique>"
                " | battle declare move <unit> to <place> with <technique>"
                " | battle declare move withdraw with <technique>"
                " | battle declare reposition <place> <dx> <dy> with <technique>"
            )
            raise CommandError(msg)

        kind = rest[0].lower()
        remainder = rest[1:]
        if "with" not in remainder:  # noqa: STRING_LITERAL
            msg = (
                "Usage: battle declare strike <unit> with <technique>"
                " | battle declare support <ally> with <technique>"
                " | battle declare rescue <ally> with <technique>"
                " | battle declare rout <unit> with <technique>"
                " | battle declare rally <unit> with <technique>"
                " | battle declare repel place <name> with <technique>"
                " | battle declare hold place <name> with <technique>"
                " | battle declare breach place <name> fortification <kind> with <technique>"
                " | battle declare fortify place <name> fortification <kind> with <technique>"
                " | battle declare set_environment [place <name>] with <technique>"
                " | battle declare move <place> with <technique>"
                " | battle declare move <unit> to <place> with <technique>"
                " | battle declare move withdraw with <technique>"
                " | battle declare reposition <place> <dx> <dy> with <technique>"
            )
            raise CommandError(msg)
        split_at = remainder.index("with")
        name = " ".join(remainder[:split_at]).strip()
        technique_name = " ".join(remainder[split_at + 1 :]).strip()

        # Dispatch table keyed by subverb rather than an if/elif chain — keeps
        # _declare's cyclomatic complexity flat as new declare kinds are added
        # (#1713 added breach/fortify, #1715 added set_environment).
        handlers: dict[str, Callable[[str, str], ActionResult]] = {
            "strike": self._declare_strike,
            "support": lambda n, t: self._declare_ally_scoped(
                BattleActionKind.SUPPORT, n, t, verb="support"
            ),
            "rescue": lambda n, t: self._declare_ally_scoped(
                BattleActionKind.RESCUE, n, t, verb="rescue"
            ),
            "rout": self._declare_rout,
            "rally": self._declare_rally,
            "repel": lambda n, t: self._declare_place_scoped(
                BattleActionKind.REPEL, n, t, verb="repel"
            ),
            "hold": lambda n, t: self._declare_place_scoped(
                BattleActionKind.HOLD, n, t, verb="hold"
            ),
            "breach": lambda n, t: self._declare_fortification_scoped(
                BattleActionKind.BREACH, n, t, verb="breach"
            ),
            "fortify": lambda n, t: self._declare_fortification_scoped(
                BattleActionKind.FORTIFY, n, t, verb="fortify"
            ),
            "set_environment": self._declare_environment,
            "move": self._declare_move,
            "reposition": self._declare_reposition,
        }
        handler = handlers.get(kind)
        if handler is None:
            msg = (
                "Unknown declare subverb. Use 'strike', 'support', 'rescue', "
                "'rout', 'rally', 'repel', 'hold', 'breach', 'fortify', "
                "'set_environment', 'move', or 'reposition'."
            )
            raise CommandError(msg)

        self._send(handler(name, technique_name))

    def _declare_unit_scoped(
        self,
        action_kind: str,
        name: str,
        technique_name: str,
        *,
        verb: str,
        own_side: bool = False,
    ) -> ActionResult:
        """Resolve and dispatch a unit/side/place-scoped declaration (STRIKE/ROUT/RALLY).

        ``name`` is the token(s) between the subverb and ``with`` — either a unit
        name, the literal ``side``, or ``place <name>``. ``own_side=True`` (RALLY)
        means ``side``/a bare unit name both resolve against the declarant's own
        side (and include ROUTED units, via ``_resolve_own_unit``) rather than the
        opposing side (STRIKE/ROUT, ACTIVE units only, via ``_resolve_unit``).
        """
        from actions.definitions.battles import DeclareBattleActionAction  # noqa: PLC0415
        from world.battles.constants import BattleActionScope  # noqa: PLC0415

        if not name:
            msg = (
                f"Declare {verb} against which unit? "
                f"(battle declare {verb} <unit> with <technique>)"
            )
            raise CommandError(msg)
        participant = self._resolve_participant()
        technique = self._resolve_technique(participant, technique_name)

        if name.lower() == "side":  # noqa: STRING_LITERAL
            if own_side:
                target_side = participant.side
            else:
                target_side = participant.battle.sides.exclude(pk=participant.side_id).first()
                if target_side is None:
                    msg = "There is no opposing side to target."
                    raise CommandError(msg)
            return DeclareBattleActionAction().run(
                self.caller,
                action_kind=action_kind,
                technique_id=technique.pk,
                scope=BattleActionScope.SIDE,
                target_side=target_side,
            )

        if name.lower().startswith(_PLACE_PREFIX):  # noqa: STRING_LITERAL
            from world.battles.models import BattlePlace  # noqa: PLC0415

            place_name = name[len(_PLACE_PREFIX) :].strip()
            place = BattlePlace.objects.filter(
                battle=participant.battle, name__iexact=place_name
            ).first()
            if place is None:
                msg = f"No front named '{place_name}' in this battle."
                raise CommandError(msg)
            return DeclareBattleActionAction().run(
                self.caller,
                action_kind=action_kind,
                technique_id=technique.pk,
                scope=BattleActionScope.PLACE,
                target_place=place,
            )

        unit = (
            self._resolve_own_unit(participant, name)
            if own_side
            else self._resolve_unit(participant, name)
        )
        return DeclareBattleActionAction().run(
            self.caller,
            action_kind=action_kind,
            technique_id=technique.pk,
            target_unit=unit,
        )

    def _declare_strike(self, name: str, technique_name: str) -> ActionResult:
        from world.battles.constants import BattleActionKind  # noqa: PLC0415

        return self._declare_unit_scoped(
            BattleActionKind.STRIKE, name, technique_name, verb="strike"
        )

    def _declare_rout(self, name: str, technique_name: str) -> ActionResult:
        from world.battles.constants import BattleActionKind  # noqa: PLC0415

        return self._declare_unit_scoped(BattleActionKind.ROUT, name, technique_name, verb="rout")

    def _declare_rally(self, name: str, technique_name: str) -> ActionResult:
        from world.battles.constants import BattleActionKind  # noqa: PLC0415

        return self._declare_unit_scoped(
            BattleActionKind.RALLY, name, technique_name, verb="rally", own_side=True
        )

    def _declare_place_scoped(
        self, action_kind: str, name: str, technique_name: str, *, verb: str
    ) -> ActionResult:
        """Resolve and dispatch a PLACE-scope-only declaration (REPEL/HOLD, #1712)."""
        from actions.definitions.battles import DeclareBattleActionAction  # noqa: PLC0415
        from world.battles.constants import BattleActionScope  # noqa: PLC0415
        from world.battles.models import BattlePlace  # noqa: PLC0415

        if not name.lower().startswith(_PLACE_PREFIX):  # noqa: STRING_LITERAL
            msg = f"Usage: battle declare {verb} place <name> with <technique>"
            raise CommandError(msg)
        place_name = name[len(_PLACE_PREFIX) :].strip()
        participant = self._resolve_participant()
        technique = self._resolve_technique(participant, technique_name)
        place = BattlePlace.objects.filter(
            battle=participant.battle, name__iexact=place_name
        ).first()
        if place is None:
            msg = f"No front named '{place_name}' in this battle."
            raise CommandError(msg)
        return DeclareBattleActionAction().run(
            self.caller,
            action_kind=action_kind,
            technique_id=technique.pk,
            scope=BattleActionScope.PLACE,
            target_place=place,
        )

    def _declare_fortification_scoped(
        self, action_kind: str, name: str, technique_name: str, *, verb: str
    ) -> ActionResult:
        """Resolve and dispatch a Fortification-scoped declaration (BREACH/FORTIFY, #1713).

        Grammar: ``place <front name> fortification <wall|gate|battlement>``. The
        extra ``fortification <kind>`` token (rather than reusing bare
        ``place <name>`` like REPEL/HOLD) is needed because a front name may
        contain spaces and a BattlePlace can carry multiple Fortification rows
        (#1713) — kind is the only free-form-ish disambiguator available, since
        Fortification has no name field of its own.
        """
        from actions.definitions.battles import DeclareBattleActionAction  # noqa: PLC0415
        from world.battles.models import BattlePlace, Fortification  # noqa: PLC0415

        usage = (
            f"Usage: battle declare {verb} place <name> fortification "
            f"<wall|gate|battlement> with <technique>"
        )
        if not name.lower().startswith(_PLACE_PREFIX):  # noqa: STRING_LITERAL
            raise CommandError(usage)
        remainder = name[len(_PLACE_PREFIX) :]
        if " fortification " not in remainder:  # noqa: STRING_LITERAL
            raise CommandError(usage)
        place_name, kind_token = remainder.split(" fortification ", 1)
        place_name = place_name.strip()
        kind_token = kind_token.strip()
        if not place_name or not kind_token:
            raise CommandError(usage)

        participant = self._resolve_participant()
        technique = self._resolve_technique(participant, technique_name)
        place = BattlePlace.objects.filter(
            battle=participant.battle, name__iexact=place_name
        ).first()
        if place is None:
            msg = f"No front named '{place_name}' in this battle."
            raise CommandError(msg)
        fort = Fortification.objects.filter(
            place=place, kind__iexact=kind_token, breached=False
        ).first()
        if fort is None:
            msg = f"No standing {kind_token} fortification at '{place_name}'."
            raise CommandError(msg)
        return DeclareBattleActionAction().run(
            self.caller,
            action_kind=action_kind,
            technique_id=technique.pk,
            target_fortification=fort,
        )

    def _declare_environment(self, name: str, technique_name: str) -> ActionResult:
        """Resolve and dispatch a SET_ENVIRONMENT declaration (#1715).

        Unlike REPEL/HOLD (PLACE-scope only, ``_declare_place_scoped``),
        SET_ENVIRONMENT is valid at BATTLE scope too — the widest scope,
        with no unit/place/side target at all. ``name`` is empty for a
        battle-wide cast, or ``place <name>`` to narrow it to one front as a
        local exception. The technique itself carries
        ``target_weather_type`` — there is no separate weather-type
        argument.
        """
        from actions.definitions.battles import DeclareBattleActionAction  # noqa: PLC0415
        from world.battles.constants import BattleActionKind, BattleActionScope  # noqa: PLC0415

        participant = self._resolve_participant()
        technique = self._resolve_technique(participant, technique_name)

        if not name:
            return DeclareBattleActionAction().run(
                self.caller,
                action_kind=BattleActionKind.SET_ENVIRONMENT,
                technique_id=technique.pk,
                scope=BattleActionScope.BATTLE,
            )

        if name.lower().startswith(_PLACE_PREFIX):  # noqa: STRING_LITERAL
            from world.battles.models import BattlePlace  # noqa: PLC0415

            place_name = name[len(_PLACE_PREFIX) :].strip()
            place = BattlePlace.objects.filter(
                battle=participant.battle, name__iexact=place_name
            ).first()
            if place is None:
                msg = f"No front named '{place_name}' in this battle."
                raise CommandError(msg)
            return DeclareBattleActionAction().run(
                self.caller,
                action_kind=BattleActionKind.SET_ENVIRONMENT,
                technique_id=technique.pk,
                scope=BattleActionScope.PLACE,
                target_place=place,
            )

        msg = "Usage: battle declare set_environment [place <name>] with <technique>"
        raise CommandError(msg)

    def _declare_move(self, name: str, technique_name: str) -> ActionResult:
        """Resolve and dispatch a MOVE declaration (#2007).

        ``name`` is one of: ``withdraw`` (self-move off the map), a bare place
        name (self-move to that front), or ``<unit> to <place>`` (a commander's
        order — requires the declarant's engaged command_tier).
        """
        from actions.definitions.battles import DeclareBattleActionAction  # noqa: PLC0415
        from world.battles.constants import BattleActionKind, BattleActionScope  # noqa: PLC0415
        from world.battles.models import BattlePlace  # noqa: PLC0415

        if not name:
            msg = (
                "Usage: battle declare move <place> with <technique>"
                " | battle declare move <unit> to <place> with <technique>"
                " | battle declare move withdraw with <technique>"
            )
            raise CommandError(msg)
        participant = self._resolve_participant()
        technique = self._resolve_technique(participant, technique_name)

        if name.lower() == "withdraw":  # noqa: STRING_LITERAL
            return DeclareBattleActionAction().run(
                self.caller,
                action_kind=BattleActionKind.MOVE,
                technique_id=technique.pk,
                scope=BattleActionScope.UNIT,
                target_place=None,
            )

        if " to " in name.lower():  # noqa: STRING_LITERAL
            split_at = name.lower().index(" to ")
            unit_name = name[:split_at].strip()
            place_name = name[split_at + len(" to ") :].strip()
            unit = self._resolve_own_unit(participant, unit_name)
            place = BattlePlace.objects.filter(
                battle=participant.battle, name__iexact=place_name
            ).first()
            if place is None:
                msg = f"No front named '{place_name}' in this battle."
                raise CommandError(msg)
            return DeclareBattleActionAction().run(
                self.caller,
                action_kind=BattleActionKind.MOVE,
                technique_id=technique.pk,
                scope=BattleActionScope.PLACE,
                target_unit=unit,
                target_place=place,
            )

        place = BattlePlace.objects.filter(battle=participant.battle, name__iexact=name).first()
        if place is None:
            msg = f"No front named '{name}' in this battle."
            raise CommandError(msg)
        return DeclareBattleActionAction().run(
            self.caller,
            action_kind=BattleActionKind.MOVE,
            technique_id=technique.pk,
            scope=BattleActionScope.UNIT,
            target_place=place,
        )

    def _declare_reposition(self, name: str, technique_name: str) -> ActionResult:
        """Resolve and dispatch a REPOSITION declaration (#1714, telnet gap closed #2007).

        ``name`` is ``<place> <dx> <dy>`` — the vehicle's own place, then the
        requested x/y delta (clamped to the vehicle's SPEED capability at
        resolution, unchanged from #1714).
        """
        from actions.definitions.battles import DeclareBattleActionAction  # noqa: PLC0415
        from world.battles.constants import BattleActionKind, BattleActionScope  # noqa: PLC0415
        from world.battles.models import BattlePlace  # noqa: PLC0415

        tokens = name.split()
        if len(tokens) < 3:  # noqa: PLR2004
            msg = "Usage: battle declare reposition <place> <dx> <dy> with <technique>"
            raise CommandError(msg)
        place_name = " ".join(tokens[:-2])
        try:
            dx = Decimal(tokens[-2])
            dy = Decimal(tokens[-1])
        except InvalidOperation as exc:
            msg = "dx and dy must be numbers."
            raise CommandError(msg) from exc

        participant = self._resolve_participant()
        technique = self._resolve_technique(participant, technique_name)
        place = BattlePlace.objects.filter(
            battle=participant.battle, name__iexact=place_name
        ).first()
        if place is None:
            msg = f"No front named '{place_name}' in this battle."
            raise CommandError(msg)
        return DeclareBattleActionAction().run(
            self.caller,
            action_kind=BattleActionKind.REPOSITION,
            technique_id=technique.pk,
            scope=BattleActionScope.PLACE,
            target_place=place,
            reposition_dx=dx,
            reposition_dy=dy,
        )

    def _declare_ally_scoped(
        self, action_kind: str, name: str, technique_name: str, *, verb: str
    ) -> ActionResult:
        """Resolve and dispatch an ally-scoped declaration (SUPPORT/RESCUE)."""
        from actions.definitions.battles import DeclareBattleActionAction  # noqa: PLC0415

        if not name:
            msg = f"{verb.capitalize()} which ally? (battle declare {verb} <ally> with <technique>)"
            raise CommandError(msg)
        participant = self._resolve_participant()
        ally = self._resolve_ally(participant, name)
        technique = self._resolve_technique(participant, technique_name)
        return DeclareBattleActionAction().run(
            self.caller,
            action_kind=action_kind,
            technique_id=technique.pk,
            target_ally=ally,
        )

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

    def _challenge_duel(self, rest: list[str]) -> None:
        from actions.definitions.battles import ChallengeChampionDuelAction  # noqa: PLC0415
        from world.battles.models import BattlePlace  # noqa: PLC0415

        if not rest:
            msg = "Usage: battle duel <front> vs <boss name>"
            raise CommandError(msg)
        participant = self._resolve_participant()
        if "vs" not in rest:  # noqa: STRING_LITERAL
            msg = "Usage: battle duel <front> vs <boss name>"
            raise CommandError(msg)
        split_at = rest.index("vs")
        place_name = " ".join(rest[:split_at]).strip()
        boss_name = " ".join(rest[split_at + 1 :]).strip()
        place = BattlePlace.objects.filter(
            battle=participant.battle, name__iexact=place_name
        ).first()
        if place is None:
            msg = f"No front named '{place_name}' in this battle."
            raise CommandError(msg)

        result = ChallengeChampionDuelAction().run(
            self.caller,
            battle_place_id=place.pk,
            opponent_kwargs={"name": boss_name, "max_health": 300, "threat_pool": None},
        )
        self._send(result)

    # ------------------------------------------------------------------
    # GM staging subverbs (#2010)

    def _resolve_staging_battle(self) -> Battle:
        """Resolve the caller's own most-recently-created, unresolved staged Battle.

        Staged battles are location-less (ADR-0081) until something else
        binds a scene location, so the staging subverbs (stage/spawn/enlist)
        can't resolve "the battle" via the caller's room the way ``battle
        round``/``resolve``/``conclude`` do (``_active_battle_in_room``).
        Instead this resolves the newest UNRESOLVED battle whose Scene the
        caller was granted ``is_gm=True`` on — the same grant
        ``CreateBattleAction`` makes at creation time.
        """
        from world.battles.constants import BattleOutcome  # noqa: PLC0415
        from world.battles.models import Battle  # noqa: PLC0415

        account = resolve_account_or_none(self.caller)
        if account is None:
            msg = "No controlling account."
            raise CommandError(msg)
        battle = (
            Battle.objects.filter(
                scene__participations__account=account,
                scene__participations__is_gm=True,
                outcome=BattleOutcome.UNRESOLVED,
            )
            .order_by("-created_at")
            .first()
        )
        if battle is None:
            msg = "You have no battle staged. Use 'battle create <name>' first."
            raise CommandError(msg)
        return battle

    def _resolve_blueprint(self, value: str) -> BattleMapBlueprint:
        from world.battles.models import BattleMapBlueprint  # noqa: PLC0415

        return resolve_model_by_pk_or_name(
            BattleMapBlueprint,
            value,
            qs=BattleMapBlueprint.objects.filter(is_active=True),
            not_found_msg=f"No active battle-map blueprint named '{value}'.",
        )

    def _resolve_template(self, value: str) -> BattleUnitTemplate:
        from world.battles.models import BattleUnitTemplate  # noqa: PLC0415

        return resolve_model_by_pk_or_name(
            BattleUnitTemplate,
            value,
            qs=BattleUnitTemplate.objects.filter(is_active=True),
            not_found_msg=f"No active battle-unit template named '{value}'.",
        )

    def _resolve_battle_place(self, battle: Battle, value: str) -> BattlePlace:
        from world.battles.models import BattlePlace  # noqa: PLC0415

        return resolve_model_by_pk_or_name(
            BattlePlace,
            value,
            qs=BattlePlace.objects.filter(battle=battle),
            not_found_msg=f"No front named '{value}' in this battle.",
        )

    def _resolve_side(self, battle: Battle, value: str) -> BattleSide:
        from world.battles.constants import BattleSideRole  # noqa: PLC0415
        from world.battles.models import BattleSide  # noqa: PLC0415

        role = value.strip().lower()
        if role not in BattleSideRole.values:
            msg = f"Unknown side '{value}'. Use 'attacker' or 'defender'."
            raise CommandError(msg)
        side = BattleSide.objects.filter(battle=battle, role=role).first()
        if side is None:
            msg = f"This battle has no {role} side."
            raise CommandError(msg)
        return side

    def _create_battle(self, rest: list[str]) -> None:
        """``battle create <name> [risk=<level>] [map=<blueprint>]`` (#2010)."""
        from actions.definitions.battles import CreateBattleAction  # noqa: PLC0415

        usage = "Usage: battle create <name> [risk=<level>] [map=<blueprint>]"
        if not rest:
            raise CommandError(usage)
        name_tokens, kv_tokens = _split_leading_positional(rest)
        name = " ".join(name_tokens).strip()
        if not name:
            raise CommandError(usage)
        kwargs, _flags = parse_kv_and_flags(
            " ".join(kv_tokens), multiword_keys=frozenset({"map"}), known_flags=frozenset()
        )

        action_kwargs: dict[str, Any] = {"name": name}
        risk_level = kwargs.get("risk")
        if risk_level:
            action_kwargs["risk_level"] = risk_level
        map_name = kwargs.get("map")
        if map_name:
            blueprint = self._resolve_blueprint(map_name)
            action_kwargs["blueprint_id"] = blueprint.pk

        result = CreateBattleAction().run(self.caller, **action_kwargs)
        self._send(result)

    def _stage_map(self, rest: list[str]) -> None:
        """``battle stage <blueprint> [replace]`` (#2010)."""
        from actions.definitions.battles import StageBattleMapAction  # noqa: PLC0415

        usage = "Usage: battle stage <blueprint> [replace]"
        if not rest:
            raise CommandError(usage)
        replace = False
        if rest[-1].lower() == "replace":  # noqa: STRING_LITERAL
            replace = True
            rest = rest[:-1]
        blueprint_name = " ".join(rest).strip()
        if not blueprint_name:
            raise CommandError(usage)

        battle = self._resolve_staging_battle()
        blueprint = self._resolve_blueprint(blueprint_name)

        result = StageBattleMapAction().run(
            self.caller, battle_id=battle.pk, blueprint_id=blueprint.pk, replace=replace
        )
        self._send(result)

    def _spawn_units(self, rest: list[str]) -> None:
        """``battle spawn <template> [count=N] [at <front>] side=<role>`` (#2010)."""
        from actions.definitions.battles import SpawnBattleUnitsAction  # noqa: PLC0415

        usage = "Usage: battle spawn <template> [count=N] [at <front>] side=<role>"
        if not rest:
            raise CommandError(usage)

        template_tokens: list[str] = []
        index = 0
        while index < len(rest) and rest[index].lower() != _AT_MARKER and "=" not in rest[index]:
            template_tokens.append(rest[index])
            index += 1
        template_name = " ".join(template_tokens).strip()
        if not template_name:
            raise CommandError(usage)

        front_tokens: list[str] = []
        kv_tokens: list[str] = []
        while index < len(rest):
            if rest[index].lower() == _AT_MARKER:
                index += 1
                while index < len(rest) and "=" not in rest[index]:
                    front_tokens.append(rest[index])
                    index += 1
            else:
                kv_tokens.append(rest[index])
                index += 1
        front_name = " ".join(front_tokens).strip()

        kwargs, _flags = parse_kv_and_flags(
            " ".join(kv_tokens), multiword_keys=frozenset(), known_flags=frozenset()
        )
        side_name = kwargs.get("side")
        if not side_name:
            raise CommandError(usage)

        battle = self._resolve_staging_battle()
        template = self._resolve_template(template_name)
        side = self._resolve_side(battle, side_name)

        action_kwargs: dict[str, Any] = {
            "battle_id": battle.pk,
            "template_id": template.pk,
            "side_id": side.pk,
        }
        count = kwargs.get("count")
        if count:
            action_kwargs["count"] = count
        if front_name:
            place = self._resolve_battle_place(battle, front_name)
            action_kwargs["place_id"] = place.pk

        result = SpawnBattleUnitsAction().run(self.caller, **action_kwargs)
        self._send(result)

    def _enlist_participant(self, rest: list[str]) -> None:
        """``battle enlist <character> = <side>[, <front>]`` (#2010)."""
        from actions.definitions.battles import EnlistBattleParticipantAction  # noqa: PLC0415

        usage = "Usage: battle enlist <character> = <side>[, <front>]"
        text = " ".join(rest).strip()
        if "=" not in text:
            raise CommandError(usage)
        character_part, _, remainder = text.partition("=")
        character_name = character_part.strip()
        side_part, _, front_part = remainder.partition(",")
        side_name = side_part.strip()
        front_name = front_part.strip()
        if not character_name or not side_name:
            raise CommandError(usage)

        battle = self._resolve_staging_battle()

        room = self.caller.location
        if room is None:
            msg = "You are not in a room."
            raise CommandError(msg)
        character_sheet = resolve_character_sheet_in_room(self.caller, character_name, room=room)

        side = self._resolve_side(battle, side_name)

        action_kwargs: dict[str, Any] = {
            "battle_id": battle.pk,
            "character_sheet_id": character_sheet.pk,
            "side_id": side.pk,
        }
        if front_name:
            place = self._resolve_battle_place(battle, front_name)
            action_kwargs["place_id"] = place.pk

        result = EnlistBattleParticipantAction().run(self.caller, **action_kwargs)
        self._send(result)

    def _browse_catalog(self, rest: list[str]) -> None:
        """``battle maps [<term>]`` / ``battle units [<term>]`` (#2010)."""
        from actions.definitions.battles import BrowseBattleCatalogAction  # noqa: PLC0415

        term = " ".join(rest).strip()
        kwargs: dict[str, Any] = {}
        if term:
            kwargs["term"] = term
        result = BrowseBattleCatalogAction().run(self.caller, **kwargs)
        self._send(result)
