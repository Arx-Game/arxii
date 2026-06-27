"""Sanctum telnet command — the ``sanctum <subverb>`` namespace (#1497).

A single command routes the seven sanctum lifecycle verbs through the shared
``dispatch_player_action`` seam — the same REGISTRY path the web uses, reaching
the existing sanctum Actions in ``actions/definitions/sanctum.py``. No new game
logic lives here; the command only parses telnet text and dispatches.

The verbs live under the ``sanctum`` namespace because several (weave, absorb) would
collide with existing bare keys. Mirrors ``CmdDuel`` (subverb routing) and
``CmdCombat`` (the namespaced status-hub pattern).

Room-presence resolution (sanctum/room_profile from caller's location) is handled
here; the Actions receive already-resolved objects so the web detail-ops keep
their no-presence-check contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

# subverb → registry action key.
_SUBVERBS: dict[str, str] = {
    "install": "sanctum_install",
    "homecoming": "sanctum_homecoming",
    "purging": "sanctum_purging",
    "weave": "sanctum_weave",
    "dissolve": "sanctum_dissolve",
    "absorb": "sanctum_absorb",
    "sever": "sanctum_sever",
}

# Slot kind token aliases — telnet input → SanctumSlotKind value.
_SLOT_MAP: dict[str, str] = {
    "personal": "PERSONAL_OWN",
    "covenant": "COVENANT",
    "helper": "HELPER",
}

# Owner mode token aliases — telnet input → owner_mode string.
_OWNER_MAP: dict[str, str] = {
    "personal": "PERSONAL",
    "covenant": "COVENANT",
}

# Subverbs whose only kwarg is the local sanctum.
_SIMPLE_ROOM_VERBS = frozenset({"dissolve", "absorb"})

# Bare ``sanctum status`` is an alias for the hub.
_STATUS_SUBVERB = "status"

# Telnet kwarg token keys used by _parse_kwargs / resolve_action_args.
_NARRATIVE_KWARG = "narrative"
_SLOT_KWARG = "slot"
_RESONANCE_KWARG = "resonance"
_OWNER_KWARG = "owner"
_AMOUNT_KWARG = "amount"
_THREAD_KWARG = "thread"


def _parse_kwargs(args: str) -> dict[str, str]:
    """Parse ``key=value`` tokens, left to right.

    ``narrative`` greedily consumes the rest of the line so narrative text may
    contain spaces. All other values are single whitespace-delimited tokens.
    Tokens that contain no ``=`` are silently skipped (positional leftovers).
    """
    out: dict[str, str] = {}
    tokens = args.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if "=" not in token:
            index += 1
            continue
        key, _, value = token.partition("=")
        if key == _NARRATIVE_KWARG:
            out[_NARRATIVE_KWARG] = " ".join([value, *tokens[index + 1 :]]).strip()
            break
        out[key] = value
        index += 1
    return out


class CmdSanctum(DispatchCommand):
    """Interact with a Sanctum — the consecrated anchor point of a mage's power.

    Usage:
        sanctum                             — list standing Sanctums + local Sanctum
        sanctum status                      — (same)
        sanctum install resonance=<name> owner=personal|covenant
                                            — consecrate the current room
        sanctum homecoming amount=<n> [narrative=<text>]
                                            — sacrifice resonance into Homecoming pool
        sanctum purging resonance=<name> amount=<n>
                                            — change the Sanctum's consecrated resonance
        sanctum weave slot=personal|covenant|helper
                                            — weave a thread into the local Sanctum
        sanctum dissolve                    — dissolve the local Sanctum
        sanctum absorb                      — drain the Sanctum's weaving pool
        sanctum sever thread=<id or name>   — retire a sanctum thread
    """

    key = "sanctum"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``sanctum``/``sanctum status`` shows the hub."""
        raw = (self.args or "").strip()
        if not raw or raw == _STATUS_SUBVERB:
            self._show_status_hub()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(_SUBVERBS)
            self.msg(f"Unknown sanctum action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's arguments into dispatch kwargs."""
        parsed = _parse_kwargs(self._rest)
        subverb = self._subverb

        if subverb in _SIMPLE_ROOM_VERBS:
            return {"sanctum": self._require_sanctum_in_room()}

        _handlers = {
            "install": self._args_install,
            "homecoming": self._args_homecoming,
            "purging": self._args_purging,
            "weave": self._args_weave,
            "sever": self._args_sever,
        }
        handler = _handlers.get(subverb)
        if handler is not None:
            return handler(parsed)
        return {}  # all subverbs gated in func(); this path is unreachable

    # -- per-subverb argument resolvers ----------------------------------------

    def _require_sanctum_in_room(self) -> Any:
        """Return the SanctumDetails for the caller's room, or raise CommandError."""
        from actions.definitions.sanctum import sanctum_in_room  # noqa: PLC0415

        s = sanctum_in_room(self.caller.location)
        if s is None:
            msg = "There is no Sanctum in this room."
            raise CommandError(msg)
        return s

    def _require_resonance(self, name: str) -> Any:
        """Resolve *name* to a Resonance (iexact), or raise CommandError."""
        from world.magic.models import Resonance  # noqa: PLC0415

        if not name:
            msg = "Specify a resonance: resonance=<name>."
            raise CommandError(msg)
        res = Resonance.objects.filter(name__iexact=name).first()
        if res is None:
            msg = f"There is no resonance called '{name}'."
            raise CommandError(msg)
        return res

    def _args_install(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve install kwargs: room_profile, resonance, owner_mode."""
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415

        resonance = self._require_resonance(parsed.get(_RESONANCE_KWARG, ""))
        owner_raw = parsed.get(_OWNER_KWARG, "").lower()
        owner_mode = _OWNER_MAP.get(owner_raw)
        if owner_mode is None:
            msg = "Usage: sanctum install resonance=<name> owner=personal|covenant."
            raise CommandError(msg)
        if self.caller.location is None:
            msg = "You are not in a room."
            raise CommandError(msg)
        room_profile = RoomProfile.objects.filter(objectdb=self.caller.location).first()
        if room_profile is None:
            msg = "This room has no room profile."
            raise CommandError(msg)
        return {
            "room_profile": room_profile,
            "resonance": resonance,
            "owner_mode": owner_mode,
        }

    def _args_homecoming(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve homecoming kwargs: sanctum, resonance_sacrificed, narrative_text."""
        sanctum = self._require_sanctum_in_room()
        amount_raw = parsed.get(_AMOUNT_KWARG, "")
        if not amount_raw or not amount_raw.isdigit():
            msg = "Usage: sanctum homecoming amount=<n> [narrative=<text>]."
            raise CommandError(msg)
        return {
            "sanctum": sanctum,
            "resonance_sacrificed": int(amount_raw),
            "narrative_text": parsed.get(_NARRATIVE_KWARG, ""),
        }

    def _args_purging(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve purging kwargs: sanctum, new_resonance, resonance_sacrificed."""
        sanctum = self._require_sanctum_in_room()
        resonance = self._require_resonance(parsed.get(_RESONANCE_KWARG, ""))
        amount_raw = parsed.get(_AMOUNT_KWARG, "")
        if not amount_raw or not amount_raw.isdigit():
            msg = "Usage: sanctum purging resonance=<name> amount=<n>."
            raise CommandError(msg)
        return {
            "sanctum": sanctum,
            "new_resonance": resonance,
            "resonance_sacrificed": int(amount_raw),
        }

    def _args_weave(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve weave kwargs: sanctum, slot_kind.

        Slot check happens before room resolution so ``weave`` with no args
        surfaces a usage error even when there's no local Sanctum.
        """
        from world.magic.constants import SanctumSlotKind  # noqa: PLC0415

        slot_raw = parsed.get(_SLOT_KWARG, "").lower()
        if not slot_raw:
            msg = "Usage: sanctum weave slot=personal|covenant|helper."
            raise CommandError(msg)
        slot_kind_str = _SLOT_MAP.get(slot_raw)
        if slot_kind_str is None:
            msg = f"Unknown slot '{slot_raw}'. Use: personal, covenant, or helper."
            raise CommandError(msg)
        slot_kind = SanctumSlotKind(slot_kind_str)
        sanctum = self._require_sanctum_in_room()
        return {
            "sanctum": sanctum,
            "slot_kind": slot_kind,
        }

    def _args_sever(self, parsed: dict[str, str]) -> dict[str, Any]:
        """Resolve sever kwargs: thread (matched by id or name on the local Sanctum)."""
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.magic.models import Thread  # noqa: PLC0415

        sanctum = self._require_sanctum_in_room()
        thread_raw = parsed.get(_THREAD_KWARG, "").strip()
        if not thread_raw:
            msg = "Usage: sanctum sever thread=<id or name>."
            raise CommandError(msg)
        sheet = self.caller.sheet_data
        qs = Thread.objects.filter(
            target_sanctum_details=sanctum,
            owner=sheet,
            target_kind=TargetKind.SANCTUM,
        )
        thread = None
        if thread_raw.isdigit():
            thread = qs.filter(pk=int(thread_raw)).first()
        if thread is None:
            thread = qs.filter(name__iexact=thread_raw).first()
        if thread is None:
            msg = f"No sanctum thread found for '{thread_raw}'."
            raise CommandError(msg)
        return {"thread": thread}

    # -- status hub ------------------------------------------------------------

    def _show_status_hub(self) -> None:
        """List the caller's standing Sanctums and note any local Sanctum."""
        from django.db.models import Q  # noqa: PLC0415

        from actions.definitions.sanctum import sanctum_in_room  # noqa: PLC0415
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.magic.models import SanctumDetails, Thread  # noqa: PLC0415

        lines = [
            "|wSanctum actions|n: install, homecoming, purging, weave, dissolve, absorb, sever"
        ]

        # getattr avoids AttributeError on objects that don't carry a sheet.
        sheet = getattr(self.caller, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is not None:
            from world.locations.models import LocationOwnership  # noqa: PLC0415
            from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

            persona = active_persona_for_sheet(sheet)
            if persona is not None:
                woven_ids = Thread.objects.filter(
                    owner=sheet,
                    target_kind=TargetKind.SANCTUM,
                    retired_at__isnull=True,
                ).values_list("target_sanctum_details_id", flat=True)
                owned_room_ids = LocationOwnership.objects.filter(
                    holder_persona=persona,
                    ended_at__isnull=True,
                ).values_list("room_profile_id", flat=True)
                sanctums = (
                    SanctumDetails.objects.select_related(
                        "feature_instance__room_profile",
                        "resonance_type",
                    )
                    .filter(
                        Q(feature_instance_id__in=woven_ids)
                        | Q(feature_instance__room_profile_id__in=owned_room_ids)
                    )
                    .distinct()
                )
                if sanctums.exists():
                    lines.append("Your standing Sanctums:")
                    for s in sanctums:
                        rtype = s.resonance_type
                        res_name = rtype.name if rtype is not None else "Unknown"
                        lines.append(f"  #{s.pk} — {res_name} Sanctum")
                else:
                    lines.append("You have no standing Sanctums.")

        local_sanctum = sanctum_in_room(self.caller.location)
        if local_sanctum is not None:
            lines.append("A Sanctum stands here.")

        self.msg("\n".join(lines))
