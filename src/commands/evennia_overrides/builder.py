"""Evennia builder command overrides with frontend metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from evennia.commands.default.building import (
    CmdDesc as EvenniaCmdDesc,
    CmdDig as EvenniaCmdDig,
    CmdLink as EvenniaCmdLink,
    CmdName as EvenniaCmdName,
    CmdOpen as EvenniaCmdOpen,
    CmdSetAttribute as EvenniaCmdSetAttribute,
    CmdSetHome as EvenniaCmdSetHome,
    CmdUnLink as EvenniaCmdUnlink,
    _desc_quit,
)
from evennia.objects.models import ObjectDB
from evennia.objects.objects import DefaultRoom
from evennia.utils.eveditor import EvEditor

from commands.frontend import FrontendMetadataMixin
from commands.frontend_types import UsageEntry
from evennia_extensions.models import ObjectDisplayData
from evennia_extensions.services.display import set_permanent_description
from server.conf.mush_markup import normalize_mush_markup
from world.character_sheets.services import rename_character, set_physical_description
from world.items.services.materialize import set_item_name
from world.locations.services import RoomEditError, set_primary_home, set_room_display_data

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

#: The switch that opens the line editor, as Evennia's CmdDesc names it.
_EDIT_SWITCH = "edit"

#: The Attribute name ``@set`` sends to the description store instead (#4338).
_DESC_ATTRIBUTE = "desc"


def write_description(obj: ObjectDB, text: str, *, edited_by: AccountDB | None) -> None:
    """Set ``obj``'s description in the store ``look`` reads for it (#4329).

    A character's is its sheet's physical description, written through the
    versioned seam so the text it replaces stays in the sheet's history. An
    item's is its instance's ``custom_description``, which overrides the
    template's. Every other object's is ``ObjectDisplayData.permanent_description``.
    Evennia's ``desc`` Attribute, which the stock command wrote, is read by nothing.
    """
    sheet = obj.character_sheet
    if sheet is not None:
        set_physical_description(sheet, text, edited_by=edited_by)
        return
    instance = obj.item_instance_or_none
    if instance is not None:
        instance.custom_description = normalize_mush_markup(text)
        instance.save(update_fields=["custom_description"])
        return
    set_permanent_description(obj, text)


def read_description(obj: ObjectDB) -> str:
    """The description ``look`` shows for ``obj``, for the line editor to start from."""
    sheet = obj.character_sheet
    if sheet is not None:
        return sheet.additional_desc or ""
    instance = obj.item_instance_or_none
    if instance is not None:
        return instance.display_description
    display = ObjectDisplayData.objects.filter(object=obj).first()
    return display.permanent_description if display else ""


def write_name(obj: ObjectDB, name: str) -> None:
    """Rename ``obj`` everywhere its name is shown (#4338).

    Evennia's ``@name`` set only the key. A character's name is also its primary
    persona's and its particled-name aliases (``rename_character``). A room's is
    also ``ObjectDisplayData.longname``, which ``where`` and the area path read
    first (``set_room_display_data``). An item's is also its instance's
    ``custom_name``, which the inventory and the web read (``set_item_name``).
    Anything else is shown by its key, and a longname it already carries is kept
    in step so the two never disagree.
    """
    sheet = obj.character_sheet
    if sheet is not None:
        rename_character(sheet, name)
        return
    instance = obj.item_instance_or_none
    if instance is not None:
        set_item_name(instance, name)
        return
    if isinstance(obj, DefaultRoom):
        set_room_display_data(room=obj, name=name, bypass_ownership=True)
        return
    obj.key = name
    display = ObjectDisplayData.objects.filter(object=obj).first()
    if display is not None and display.longname:
        display.longname = name
        display.save(update_fields=["longname"])


def _desc_load(caller: ObjectDB) -> str:
    return read_description(caller.db.evmenu_target)


def _desc_save(caller: ObjectDB, buf: str) -> bool:
    """Save the editor's buffer as the target's description; True tells EvEditor it saved."""
    write_description(caller.db.evmenu_target, buf, edited_by=caller.account)
    caller.msg("Saved.")
    return True


def _open_desc_editor(caller: ObjectDB, obj: ObjectDB) -> None:
    """Open the line editor on ``obj``'s description: ``desc/edit`` and ``@set/edit .../desc``."""
    caller.db.evmenu_target = obj
    EvEditor(
        caller,
        loadfunc=_desc_load,
        savefunc=_desc_save,
        quitfunc=_desc_quit,
        key="desc",
        persistent=True,
    )


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
        _open_desc_editor(self.caller, obj)

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


class CmdName(EvenniaCmdName):
    """
    change the name and/or aliases of an object

    Usage:
      name <obj> = <newname>;alias1;alias2

    Renames the object everywhere its name shows: a character's name and
    persona, a room's name in look and where, an item's name in look and in
    the inventory. Aliases after ; are extra names to find it by. Use *obj to
    rename an account.
    """

    def func(self) -> None:
        """Evennia's flow, with the new name sent through ``write_name`` (#4338)."""
        caller = self.caller
        if not self.args or not self.lhs_objs:
            caller.msg("Usage: name <obj> = <newname>[;alias;alias;...]")
            return
        objname = self.lhs_objs[0]["name"]
        if objname.startswith("*"):
            # An account's username is Evennia's own field and nothing of ours shadows it.
            super().func()
            return
        obj = caller.search(objname)
        if not obj:
            return
        newname, aliases = self._new_name_and_aliases()
        if not newname and not aliases:
            caller.msg("No names or aliases defined!")
            return
        if not (obj.access(caller, "control") or obj.access(caller, "edit")):
            caller.msg(f"You don't have the right to edit {obj}.")
            return
        if newname:
            write_name(obj, newname)
        for alias in aliases:
            obj.aliases.add(alias)
        if obj.destination:
            # An exit's command is built from its key; Evennia refreshes it this way.
            obj.flush_from_cache(force=True)
        alias_note = f" ({', '.join(aliases)})" if aliases else ""
        caller.msg(f"Object's name changed to '{newname}'{alias_note}.")

    def _new_name_and_aliases(self) -> tuple[str, list[str]]:
        """The name and aliases after ``=``, the way Evennia's parser split them."""
        if self.rhs_objs:
            return self.rhs_objs[0]["name"], self.rhs_objs[0]["aliases"] or []
        return self.rhs or "", []


class CmdSetHome(EvenniaCmdSetHome):
    """
    set an object's home location

    Usage:
      sethome <obj> [= <home_location>]

    A character's home is where it lives: the room becomes the primary home
    of the face the character is wearing, which is also where it recalls to
    and rests. That face needs a tenancy in the room first. Any other
    object's home is where it goes if its location disappears. With no
    location, shows the current home.
    """

    def func(self) -> None:
        """A character's home goes through ``set_primary_home`` (#4338); anything else is stock."""
        if not self.args or not self.rhs:
            super().func()
            return
        caller = self.caller
        obj = caller.search(self.lhs, global_search=True)
        if not obj:
            return
        sheet = obj.character_sheet
        if sheet is None:
            # Evennia's home is the only home a non-character has.
            super().func()
            return
        room = caller.search(self.rhs, global_search=True)
        if not room:
            return
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        try:
            persona = active_persona_for_sheet(sheet)
        except Persona.DoesNotExist:
            caller.msg(f"{obj.key} has no face to give a home to.")
            return
        try:
            set_primary_home(persona=persona, room=room)
        except RoomEditError as exc:
            caller.msg(f"{obj.key}'s home was not changed: {exc.user_message}")
            return
        caller.msg(f"{obj.key}'s home is now {room.key}, as {persona.name}.")


class CmdSetAttribute(EvenniaCmdSetAttribute):
    """
    set attribute on an object or account

    Usage:
      set[/switch] <obj>/<attr>[:category] = <value>
      set[/switch] <obj>/<attr>[:category] =                  # delete attribute
      set[/switch] <obj>/<attr>[:category]                    # view attribute
      set[/switch] *<account>/<attr>[:category] = <value>

    Switch:
        edit: Open the line editor (string values only)
        script: If we're trying to set an attribute on a script
        channel: If we're trying to set an attribute on a channel
        account: If we're trying to set an attribute on an account
        room: Setting an attribute on a room (global search)
        exit: Setting an attribute on an exit (global search)
        char: Setting an attribute on a character (global search)
        character: Alias for char, as above.

    Example:
        set self/foo = "bar"
        set/delete self/foo
        set self/foo = $dbref(#53)

    <obj>/desc is the description look shows, the same one the desc command
    sets: a character's goes to its sheet, an item's to the item. Every other
    attribute is an Evennia Attribute on the object.

    Values starting with ', ", (, [ or { are stored as Python primitives and
    must be written in Python syntax. Use $dbref(#dbref) or $search(key) to
    store an object. You need control or edit access to the object.
    """

    def _is_description(self, obj: object, attr: str, category: str | None) -> bool:
        """``<obj>/desc`` on a game object is its description, not an Attribute (#4338)."""
        return attr == _DESC_ATTRIBUTE and category is None and isinstance(obj, ObjectDB)

    def func(self) -> None:
        """``set <obj>/desc = <text>`` stores the text as typed (#4338).

        Evennia's flow reads every value as a Python literal first, so prose came
        back with a "was converted to a string" warning and quoted text lost its
        quotes. A description is always text, so that one form is handled here;
        everything else, including several attributes at once, is Evennia's.
        """
        if not self.args or not self.rhs or _EDIT_SWITCH in self.switches:
            super().func()
            return
        target = self.lhs_objattr[0]
        if target["attrs"] != [_DESC_ATTRIBUTE] or self.lhs_objs[0].get("option"):
            super().func()
            return
        obj = self.search_for_obj(target["name"])
        if not obj:
            return
        if not isinstance(obj, ObjectDB):
            super().func()
            return
        if not self.check_obj(obj):
            return
        if not (obj.access(self.caller, "control") or obj.access(self.caller, "edit")):
            self.caller.msg(f"You don't have permission to edit {obj.key}.")
            return
        write_description(obj, self.rhs, edited_by=self.account)
        self.caller.msg(f"Set the description of {obj.name}.")

    def view_attr(self, obj: Any, attr: str, category: str | None) -> str:
        if self._is_description(obj, attr, category):
            return f"\nDescription of {obj.name}: {read_description(obj)}"
        return super().view_attr(obj, attr, category)

    def rm_attr(self, obj: Any, attr: str, category: str | None) -> str:
        if self._is_description(obj, attr, category):
            write_description(obj, "", edited_by=self.account)
            return f"\nCleared the description of {obj.name}."
        return super().rm_attr(obj, attr, category)

    def set_attr(self, obj: Any, attr: str, value: Any, category: str | None) -> str:
        if self._is_description(obj, attr, category):
            write_description(obj, str(value), edited_by=self.account)
            return f"\nSet the description of {obj.name}."
        return super().set_attr(obj, attr, value, category)

    def edit_handler(self, obj: Any, attr: str, caller: ObjectDB) -> None:
        # The edit switch takes no category; Evennia's own editor ignores it too.
        if self._is_description(obj, attr, category=None):
            _open_desc_editor(caller, obj)
            return
        super().edit_handler(obj, attr, caller)


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
