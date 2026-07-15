"""Companion telnet command — the ``companion <subverb>`` namespace (#1918).

Routes the companion lifecycle verbs through ``dispatch_player_action`` — the
same REGISTRY seam the web uses. No new game logic lives here.

Mirrors ``CmdSanctum`` (subverb routing + status-hub pattern). The verbs live
under the ``companion`` namespace because several (bind, release) would collide
with existing bare keys.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand, parse_greedy_kwargs
from commands.exceptions import CommandError
from world.companions.constants import CompanionOrderKind

if TYPE_CHECKING:
    from actions.types import ActionRef

# subverb → registry action key.
_SUBVERBS: dict[str, str] = {
    "bind": "bind_companion",
    "fight": "companion_fight",
    "deploy": "deploy_companion",
    "release": "release_companion",
    "order": "order_companion",
    "mount": "mount_companion",
    "dismount": "dismount_companion",
}
# "list" and "status" are handled locally (status hub), not dispatched.

# Bare ``companion status`` / ``companion list`` are aliases for the hub.
_HUB_SUBVERBS = frozenset({"status", "list"})

# Telnet kwarg token keys used by resolve_action_args.
_ARCHETYPE_KWARG = "archetype"
_GIFT_KWARG = "gift"
_NAME_KWARG = "name"

_MAX_NAME_LENGTH = 100

# Subverbs whose only kwarg is bind's parsed kwargs.
_BIND_SUBVERB = "bind"

# Subverbs that take a single bare companion identifier (positional, not key=value).
_POSITIONAL_SUBVERBS = frozenset({"release", "fight", "deploy", "mount"})
# "dismount" takes no argument — it dismounts whatever the caller is riding.

# The order subverb has its own multi-token parser.
_ORDER_SUBVERB = "order"
_MIN_ORDER_TOKENS = 2  # <name> <verb>
_MIN_ATTACK_TOKENS = 3  # <name> attack <target>
_MIN_ATTACK_WITH_ABILITY_TOKENS = 5  # <name> attack <target> with <ability>
_ORDER_ATTACK = "attack"
_ORDER_HOLD = "hold"
_ORDER_DEFEND = "defend"
_ORDER_WITH = "with"


class CmdCompanion(DispatchCommand):
    """Manage your bonded companions — bind, release, fight, deploy, order, mount (#1918,
    #1921, #1843).

    Usage:
        companion                             — list active companions + capacity
        companion status                      — (same)
        companion list                        — (same)
        companion bind archetype=<name|id> gift=<name|id> name=<text>
                                              — bind a new companion
        companion release <name|id>           — release a bonded companion
        companion fight <name|id>             — commit a companion into combat
        companion deploy <name|id>            — deploy a companion into a battle
        companion order <name> attack <target> [with <ability>]
                                              — direct a deployed companion
        companion order <name> hold           — tell a companion to hold
        companion order <name> defend <ally>  — tell a companion to defend an ally
        companion mount <name|id>             — mount a ridable companion
        companion dismount                    — dismount your current mount

    ``name=`` must be the final token on ``bind`` (it greedily consumes the rest
    of the line so names with spaces work).
    """

    key = "companion"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``companion``/``status``/``list`` shows the hub."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() in _HUB_SUBVERBS:
            self._show_status_hub()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(_SUBVERBS)
            self.msg(f"Unknown companion action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's arguments into dispatch kwargs."""
        if self._subverb == _BIND_SUBVERB:
            return self._args_bind(parse_greedy_kwargs(self._rest, greedy_key=_NAME_KWARG))
        if self._subverb == _ORDER_SUBVERB:
            return self._args_order(self._rest)
        if self._subverb in _POSITIONAL_SUBVERBS:
            return {"companion_id": self._resolve_companion_id(self._rest)}
        return {}  # all subverbs gated in func(); this path is unreachable

    # -- per-subverb argument resolvers ----------------------------------------

    def _sheet(self) -> Any:
        """Return the caller's CharacterSheet, or raise CommandError if none."""
        sheet = self.caller.character_sheet
        if sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)
        return sheet

    @staticmethod
    def _resolve_by_name_or_pk(qs: Any, value: str, *, pk_field: str, name_field: str) -> Any:
        """Resolve *value* (digit → pk lookup, else iexact name) on *qs*.

        Returns the first match or None. The caller validates and raises
        ``CommandError`` with a context-specific message on None.
        """
        if value.isdigit():
            return qs.filter(**{pk_field: int(value)}).first()
        return qs.filter(**{name_field: value}).first()

    def _resolve_archetype(self, value: str) -> Any:
        """Resolve *value* (name iexact or pk) to a CompanionArchetype."""
        from world.companions.models import CompanionArchetype  # noqa: PLC0415

        if not value:
            msg = "Specify an archetype: archetype=<name|id>."
            raise CommandError(msg)
        archetype = self._resolve_by_name_or_pk(
            CompanionArchetype.objects,
            value,
            pk_field="pk",
            name_field="name__iexact",
        )
        if archetype is None:
            msg = f"No companion archetype found for '{value}'."
            raise CommandError(msg)
        return archetype

    def _resolve_owned_gift(self, value: str) -> Any:
        """Resolve *value* (gift name iexact or pk) to a CharacterGift owned by the caller.

        Scopes the lookup to ``CharacterGift.objects.filter(character=sheet)`` so
        the caller can never reference a gift they don't own.
        """
        from world.magic.models.gifts import CharacterGift  # noqa: PLC0415

        if not value:
            msg = "Specify a gift: gift=<name|id>."
            raise CommandError(msg)
        sheet = self._sheet()
        char_gift = self._resolve_by_name_or_pk(
            CharacterGift.objects.filter(character=sheet),
            value,
            pk_field="gift_id",
            name_field="gift__name__iexact",
        )
        if char_gift is None:
            msg = f"You do not own a gift matching '{value}'."
            raise CommandError(msg)
        return char_gift.gift

    def _resolve_companion_id(self, value: str) -> int:
        """Resolve *value* (companion name iexact or pk) to a pk of an active owned companion."""
        from world.companions.models import Companion  # noqa: PLC0415

        value = value.strip()
        if not value:
            msg = f"Specify a companion: companion {self._subverb} <name|id>."
            raise CommandError(msg)
        sheet = self._sheet()
        companion = self._resolve_by_name_or_pk(
            Companion.objects.filter(owner=sheet, released_at__isnull=True),
            value,
            pk_field="pk",
            name_field="name__iexact",
        )
        if companion is None:
            msg = f"No active companion found for '{value}'."
            raise CommandError(msg)
        return companion.pk

    def _args_bind(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve bind kwargs: archetype_id, gift_id, name."""
        archetype = self._resolve_archetype(parsed.get(_ARCHETYPE_KWARG, ""))
        gift = self._resolve_owned_gift(parsed.get(_GIFT_KWARG, ""))
        name = parsed.get(_NAME_KWARG, "").strip()
        if not name:
            msg = "Specify a name: name=<text> (must be the final token)."
            raise CommandError(msg)
        if len(name) > _MAX_NAME_LENGTH:
            msg = "Companion names must be 100 characters or fewer."
            raise CommandError(msg)
        return {
            "archetype_id": archetype.pk,
            "gift_id": gift.pk,
            "name": name,
        }

    def _args_order(self, rest: str) -> dict[str, Any]:
        """Parse ``order <name> <verb> [target] [with <ability>]`` into kwargs.

        Verbs: attack <target> [with <ability>], hold, defend <ally>.
        """
        parts = rest.split()
        if len(parts) < _MIN_ORDER_TOKENS:
            msg = "Usage: companion order <name> <attack|hold|defend> [target]"
            raise CommandError(msg)

        companion_id = self._resolve_companion_id(parts[0])
        verb = parts[1].lower()

        if verb == _ORDER_HOLD:
            return {"companion_id": companion_id, "order_kind": CompanionOrderKind.HOLD}

        if verb == _ORDER_ATTACK:
            if len(parts) < _MIN_ATTACK_TOKENS:
                msg = "Usage: companion order <name> attack <target> [with <ability>]"
                raise CommandError(msg)
            target_name = parts[2]
            target_id = self._resolve_order_target(target_name)
            kwargs: dict[str, Any] = {
                "companion_id": companion_id,
                "order_kind": CompanionOrderKind.ATTACK_TARGET,
                "target_id": target_id,
            }
            # Optional: with <ability>
            if len(parts) >= _MIN_ATTACK_WITH_ABILITY_TOKENS and parts[3].lower() == _ORDER_WITH:
                ability_id = self._resolve_order_ability(parts[4], companion_id)
                kwargs["ability_id"] = ability_id
            return kwargs

        if verb == _ORDER_DEFEND:
            if len(parts) < _MIN_ATTACK_TOKENS:
                msg = "Usage: companion order <name> defend <ally>"
                raise CommandError(msg)
            ally_name = parts[2]
            ally_id = self._resolve_order_ally(ally_name)
            return {
                "companion_id": companion_id,
                "order_kind": CompanionOrderKind.DEFEND_ALLY,
                "ally_id": ally_id,
            }

        msg = f"Unknown order verb '{verb}'. Try: attack, hold, defend."
        raise CommandError(msg)

    def _resolve_order_target(self, name: str) -> int:
        """Resolve a target name/pk to a CombatOpponent or BattleUnit pk."""
        from world.combat.models import CombatOpponent  # noqa: PLC0415

        if name.isdigit():
            # Could be a CombatOpponent or BattleUnit; the Action resolves it
            return int(name)
        # Try CombatOpponent by name (iexact)
        opponent = CombatOpponent.objects.filter(name__iexact=name).first()
        if opponent is not None:
            return opponent.pk
        msg = f"No target found for '{name}'."
        raise CommandError(msg)

    def _resolve_order_ability(self, name: str, companion_id: int) -> int:
        """Resolve an ability name/pk on the companion's archetype."""
        from world.companions.models import Companion, CompanionAbility  # noqa: PLC0415

        companion = Companion.objects.get(pk=companion_id)
        if name.isdigit():
            ability = CompanionAbility.objects.filter(
                pk=int(name), archetype=companion.archetype
            ).first()
        else:
            ability = CompanionAbility.objects.filter(
                name__iexact=name, archetype=companion.archetype
            ).first()
        if ability is None:
            msg = f"No ability '{name}' found for {companion.name}."
            raise CommandError(msg)
        return ability.pk

    def _resolve_order_ally(self, name: str) -> int:
        """Resolve an ally name/pk to a CombatParticipant or BattleParticipant pk."""
        from world.combat.models import CombatParticipant  # noqa: PLC0415

        if name.isdigit():
            return int(name)
        # Try CombatParticipant by character name
        participant = CombatParticipant.objects.filter(
            character_sheet__character__db_key__iexact=name
        ).first()
        if participant is not None:
            return participant.pk
        msg = f"No ally found for '{name}'."
        raise CommandError(msg)

    # -- status hub ------------------------------------------------------------

    def _show_status_hub(self) -> None:
        """List the caller's active companions + remaining capacity per gift."""
        lines = ["|wCompanion actions|n: bind, release, fight, deploy, order, mount, dismount"]

        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg("\n".join(lines))
            return

        active = self.caller.companions.active()
        if not active:
            lines.append("You have no active companions.")
        else:
            lines.append("Your active companions:")
            lines.extend(
                f"  #{c.pk} — {c.name} ({c.archetype.name}, cost {c.archetype.capacity_cost})"
                for c in active
            )

        lines.extend(self._capacity_lines(sheet))
        self.msg("\n".join(lines))

    def _capacity_lines(self, sheet: Any) -> list[str]:
        """Lines showing remaining Companion Capacity per granting gift."""
        from world.companions.services import (  # noqa: PLC0415
            NoCompanionThreadError,
            companion_capacity,
            used_companion_capacity,
        )

        lines: list[str] = []
        for char_gift in sheet.character_gifts.all():
            gift = char_gift.gift
            try:
                used = used_companion_capacity(sheet, gift)
                total = companion_capacity(sheet, gift)
            except NoCompanionThreadError:
                continue  # gift has no GIFT thread → no capacity to show
            remaining = total - used
            lines.append(f"  {gift.name}: {used}/{total} capacity ({remaining} remaining)")
        return lines
