"""Outfit telnet command — the ``outfit <subverb>`` namespace (#1866).

Routes save/rename/delete/addslot/removeslot through the new outfit CRUD
Actions, and wear/undress/present through the already-built
ApplyOutfitAction/UndressAction/PresentOutfitAction — the same Actions the
web ViewSets now dispatch through (#1866 refactor, Task 7).
"""

from __future__ import annotations

from typing import Any

from actions.definitions.fashion import PresentOutfitAction
from actions.definitions.outfits import (
    AddOutfitSlotAction,
    ApplyOutfitAction,
    DeleteOutfitAction,
    RemoveOutfitSlotAction,
    RenameOutfitAction,
    SaveOutfitAction,
    UndressAction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = (
    "Usage: outfit save <name> wardrobe=<id> | outfit rename <id>=<name> | "
    "outfit delete <id> | outfit addslot <id> item=<id> region=<region> "
    "layer=<layer> | outfit removeslot <id> region=<region> layer=<layer> | "
    "outfit wear <id> | outfit undress | outfit present <id> event=<event id>"
)


def _parse_kwargs(rest: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in rest.split():
        if "=" in token:
            key, _, value = token.partition("=")
            out[key] = value
    return out


def _leading_text(rest: str) -> str:
    words = []
    for token in rest.split():
        if "=" in token:
            break
        words.append(token)
    return " ".join(words)


class CmdOutfit(ArxCommand):
    """Manage saved outfits: save, rename, delete, edit slots, wear, present.

    Usage:
        outfit / outfit list
        outfit save <name> wardrobe=<item id>
        outfit rename <id>=<new name>
        outfit delete <id>
        outfit addslot <id> item=<item id> region=<region> layer=<layer>
        outfit removeslot <id> region=<region> layer=<layer>
        outfit wear <id>
        outfit undress
        outfit present <id> event=<event id>
    """

    key = "outfit"
    locks = "cmd:all()"

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw or raw.lower() == "list":  # noqa: STRING_LITERAL
            self._show_hub()
            return
        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        handler = {
            "save": self._do_save,
            "rename": self._do_rename,
            "delete": self._do_delete,
            "addslot": self._do_addslot,
            "removeslot": self._do_removeslot,
            "wear": self._do_wear,
            "undress": self._do_undress,
            "present": self._do_present,
        }.get(subverb)
        if handler is None:
            self.msg(f"Unknown outfit action '{subverb}'. {_USAGE}")
            return
        try:
            handler(rest)
        except CommandError as err:
            self.msg(str(err))

    def _show_hub(self) -> None:
        from world.items.models import Outfit  # noqa: PLC0415

        sheet = getattr(self.caller, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            self.msg("You have no character sheet.")
            return
        outfits = list(Outfit.objects.filter(character_sheet=sheet).order_by("name"))
        if not outfits:
            self.msg("You have no saved outfits.")
            return
        lines = ["Your saved outfits:"]
        lines.extend(f"  #{o.pk} — {o.name}" for o in outfits)
        self.msg("\n".join(lines))

    def _resolve_outfit(self, id_raw: str) -> Any:
        from world.items.models import Outfit  # noqa: PLC0415

        if not id_raw.isdigit():
            raise CommandError(_USAGE)
        outfit = Outfit.objects.filter(pk=int(id_raw)).first()
        if outfit is None:
            msg = "No such outfit."
            raise CommandError(msg)
        return outfit

    # `use_dbref=True` is required below: Evennia's `search()` gates dbref
    # (`#123`) lookups behind a Builder-permission lock by default
    # (`use_dbref=None` → checks `perm(Builder)`), so a bare `#{id}` search
    # would silently fail to match for ordinary players. It's safe here
    # because `location=self.caller` already scopes the search to items the
    # caller physically holds — this can't be used to reference another
    # player's or room's objects by id.

    def _do_save(self, rest: str) -> None:
        kwargs = _parse_kwargs(rest)
        name = _leading_text(rest)
        wardrobe_id = kwargs.get("wardrobe", "")
        if not name or not wardrobe_id.isdigit():
            raise CommandError(_USAGE)
        wardrobe_obj = self.caller.search(f"#{wardrobe_id}", location=self.caller, use_dbref=True)
        if not wardrobe_obj:
            msg = "You aren't holding that wardrobe."
            raise CommandError(msg)
        result = SaveOutfitAction().run(actor=self.caller, wardrobe=wardrobe_obj, name=name)
        if result.message:
            self.msg(result.message)
        elif result.success:
            self.msg(f"Saved outfit '{name}'.")

    def _do_rename(self, rest: str) -> None:
        id_part, _, name = rest.partition("=")
        outfit = self._resolve_outfit(id_part.strip())
        name = name.strip()
        if not name:
            raise CommandError(_USAGE)
        result = RenameOutfitAction().run(actor=self.caller, outfit=outfit, name=name)
        if result.message:
            self.msg(result.message)
        elif result.success:
            self.msg(f"Renamed to '{name}'.")

    def _do_delete(self, rest: str) -> None:
        outfit = self._resolve_outfit(rest.strip())
        result = DeleteOutfitAction().run(actor=self.caller, outfit=outfit)
        if result.message:
            self.msg(result.message)
        elif result.success:
            self.msg("Outfit deleted.")

    def _do_addslot(self, rest: str) -> None:
        parts = rest.split(maxsplit=1)
        if not parts:
            raise CommandError(_USAGE)
        outfit = self._resolve_outfit(parts[0])
        kwargs = _parse_kwargs(parts[1] if len(parts) > 1 else "")
        item_id = kwargs.get("item", "")
        region = kwargs.get("region", "")
        layer = kwargs.get("layer", "")
        if not item_id.isdigit() or not region or not layer:
            raise CommandError(_USAGE)
        item_obj = self.caller.search(f"#{item_id}", location=self.caller, use_dbref=True)
        if not item_obj:
            msg = "You aren't holding that item."
            raise CommandError(msg)
        result = AddOutfitSlotAction().run(
            actor=self.caller,
            outfit=outfit,
            item=item_obj,
            body_region=region,
            equipment_layer=layer,
        )
        if result.message:
            self.msg(result.message)
        elif result.success:
            self.msg("Slot added.")

    def _do_removeslot(self, rest: str) -> None:
        parts = rest.split(maxsplit=1)
        if not parts:
            raise CommandError(_USAGE)
        outfit = self._resolve_outfit(parts[0])
        kwargs = _parse_kwargs(parts[1] if len(parts) > 1 else "")
        region = kwargs.get("region", "")
        layer = kwargs.get("layer", "")
        if not region or not layer:
            raise CommandError(_USAGE)
        result = RemoveOutfitSlotAction().run(
            actor=self.caller, outfit=outfit, body_region=region, equipment_layer=layer
        )
        if result.message:
            self.msg(result.message)
        elif result.success:
            self.msg("Slot removed.")

    def _do_wear(self, rest: str) -> None:
        if not rest.strip().isdigit():
            raise CommandError(_USAGE)
        result = ApplyOutfitAction().run(actor=self.caller, outfit_id=int(rest.strip()))
        if result.message:
            self.msg(result.message)

    def _do_undress(self, rest: str) -> None:
        result = UndressAction().run(actor=self.caller)
        if result.message:
            self.msg(result.message)

    def _do_present(self, rest: str) -> None:
        parts = rest.split(maxsplit=1)
        if not parts or not parts[0].isdigit():
            raise CommandError(_USAGE)
        outfit_id = int(parts[0])
        kwargs = _parse_kwargs(parts[1] if len(parts) > 1 else "")
        event_id_raw = kwargs.get("event", "")
        if not event_id_raw.isdigit():
            msg = "Usage: outfit present <id> event=<event id>."
            raise CommandError(msg)
        result = PresentOutfitAction().run(
            actor=self.caller, outfit_id=outfit_id, event_id=int(event_id_raw)
        )
        if result.message:
            self.msg(result.message)
