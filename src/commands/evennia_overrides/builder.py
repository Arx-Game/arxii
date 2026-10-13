"""Evennia builder command overrides with frontend metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from evennia.commands.default.building import (
    CmdDesc as EvenniaCmdDesc,
    CmdDig as EvenniaCmdDig,
    CmdLink as EvenniaCmdLink,
    CmdOpen as EvenniaCmdOpen,
    CmdUnLink as EvenniaCmdUnlink,
    _desc_quit,
)
from evennia.utils.eveditor import EvEditor

from commands.frontend import FrontendMetadataMixin
from commands.frontend_types import UsageEntry
from evennia_extensions.models import ObjectDisplayData
from evennia_extensions.services.display import set_permanent_description
from world.character_sheets.services import set_physical_description

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

#: The switch that opens the line editor, as Evennia's CmdDesc names it.
_EDIT_SWITCH = "edit"


def write_description(obj: ObjectDB, text: str, *, edited_by: AccountDB | None) -> None:
    """Set ``obj``'s description in the store ``look`` reads for it (#4329).

    A character's is its sheet's physical description, written through the
    versioned seam so the text it replaces stays in the sheet's history. Every
    other object's is ``ObjectDisplayData.permanent_description``. Evennia's
    ``desc`` Attribute, which the stock command wrote, is read by nothing.
    """
    sheet = obj.character_sheet
    if sheet is not None:
        set_physical_description(sheet, text, edited_by=edited_by)
    else:
        set_permanent_description(obj, text)


def read_description(obj: ObjectDB) -> str:
    """The description ``write_description`` would replace, for the line editor."""
    sheet = obj.character_sheet
    if sheet is not None:
        return sheet.additional_desc or ""
    display = ObjectDisplayData.objects.filter(object=obj).first()
    return display.permanent_description if display else ""


def _desc_load(caller: ObjectDB) -> str:
    return read_description(caller.db.evmenu_target)


def _desc_save(caller: ObjectDB, buf: str) -> bool:
    """Save the editor's buffer as the target's description; True tells EvEditor it saved."""
    write_description(caller.db.evmenu_target, buf, edited_by=caller.account)
    caller.msg("Saved.")
    return True


class CmdDesc(EvenniaCmdDesc):
    """
    describe an object or the current room.

    Usage:
      desc [<obj> =] <description>

    Switches:
      edit - Open up a line editor for more advanced editing.

    Sets the description look shows. With no object, describes the current room.
    """

    def edit_handler(self) -> None:
        """Evennia's editor flow, loading and saving the description look reads."""
        if self.rhs:
            self.msg("|rYou may specify a value, or use the edit switch, but not both.|n")
            return
        if self.args:
            obj = self.caller.search(self.args)
        else:
            obj = self.caller.location or self.msg("|rYou can't describe oblivion.|n")
        if not obj:
            return
        if not self._may_describe(obj):
            self.msg(f"You don't have permission to edit the description of {obj.key}.")
            return
        self.caller.db.evmenu_target = obj
        EvEditor(
            self.caller,
            loadfunc=_desc_load,
            savefunc=_desc_save,
            quitfunc=_desc_quit,
            key="desc",
            persistent=True,
        )

    def func(self) -> None:
        """Evennia's flow, with the write sent to the store look reads."""
        caller = self.caller
        if not self.args and _EDIT_SWITCH not in self.switches:
            caller.msg("Usage: desc [<obj> =] <description>")
            return
        if _EDIT_SWITCH in self.switches:
            self.edit_handler()
            return
        if "=" in self.args:
            obj = caller.search(self.lhs)
            if not obj:
                return
            text = self.rhs or ""
        else:
            obj = caller.location or self.msg("|rYou don't have a location to describe.|n")
            if not obj:
                return
            text = self.args
        if not self._may_describe(obj):
            caller.msg(f"You don't have permission to edit the description of {obj.key}.")
            return
        write_description(obj, text, edited_by=self.account)
        caller.msg(f"The description was set on {obj.get_display_name(caller)}.")

    def _may_describe(self, obj: ObjectDB) -> bool:
        return obj.access(self.caller, "control") or obj.access(self.caller, "edit")


class CmdDig(FrontendMetadataMixin, EvenniaCmdDig):
    """Create a new room and optional connecting exits."""

    usage: ClassVar[list[UsageEntry]] = [
        {
            "prompt": "@dig room_name=exit_name, back_exit",
            "params_schema": {
                "room_name": {"type": "string"},
                "exit_name": {"type": "string"},
                "back_exit": {"type": "string", "required": False},
            },
        },
    ]


class CmdOpen(FrontendMetadataMixin, EvenniaCmdOpen):
    """Create an exit from the current room."""

    usage: ClassVar[list[UsageEntry]] = [
        {
            "prompt": "@open exit_name=destination",
            "params_schema": {
                "exit_name": {"type": "string"},
                "destination": {"type": "string"},
            },
        },
    ]


class CmdLink(FrontendMetadataMixin, EvenniaCmdLink):
    """Link an existing exit to a destination."""

    usage: ClassVar[list[UsageEntry]] = [
        {
            "prompt": "@link exit_name=destination",
            "params_schema": {
                "exit_name": {"type": "string"},
                "destination": {"type": "string"},
            },
        },
    ]


class CmdUnlink(FrontendMetadataMixin, EvenniaCmdUnlink):
    """Remove the destination from an exit."""

    usage: ClassVar[list[UsageEntry]] = [
        {
            "prompt": "unlink exit_name",
            "params_schema": {"exit_name": {"type": "string"}},
        },
    ]
