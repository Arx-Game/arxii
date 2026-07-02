"""Player-facing room actions — the room-editor MVP seam (#1470) + the Room Builder (#670).

``RoomEditAction`` lets a room **owner** edit the room they're standing in: its
display name, description, and public/private listing. It is the single seam both
telnet (``CmdManageRoom``) and the web (action-dispatch + ``RoomEditorPanel``)
call. Ownership is gated by ``IsRoomOwnerPrerequisite``; the write + the
public-toggle guard live in ``world.locations.services.set_room_display_data``.

The Room Builder actions (#670) follow the same shape: thin dispatch over
``world.buildings.room_services`` / ``world.locations.services``, permission
re-checked in the service, per-operation prerequisites (owner structural /
tenant redescribe — relationship, not lifecycle). Structural success messages
carry the space budget (``Space: used/total``) per the ratified UX.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import (
    HasCharacterSheetPrerequisite,
    IsRoomOwnerPrerequisite,
    IsRoomTenantPrerequisite,
    Prerequisite,
)
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from actions.types import ActionContext


@dataclass
class RoomEditAction(Action):
    """Owner edits the room they're standing in: name, description, public/private.

    Operates on ``actor.location`` (the room the actor is in). Each field is
    optional — only those supplied are changed.
    """

    key: str = "edit_room"
    name: str = "Edit Room"
    icon: str = "home"
    category: str = "locations"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.locations.services import (  # noqa: PLC0415
            RoomEditError,
            set_room_display_data,
        )
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        persona = active_persona_for_sheet(actor.sheet_data)
        try:
            set_room_display_data(
                room=room,
                persona=persona,
                name=kwargs.get("name"),
                description=kwargs.get("description"),
                is_public=kwargs.get("is_public"),
            )
        except RoomEditError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Room updated.")


def _persona_for(actor: ObjectDB):
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    return active_persona_for_sheet(actor.sheet_data)


def _resolve_room(actor: ObjectDB, kwargs: dict[str, Any]) -> ObjectDB | None:
    """The action's anchor room: explicit ``room_id`` (web canvas) else ``actor.location``."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    room_id = kwargs.get("room_id")
    if room_id:
        profile = RoomProfile.objects.filter(objectdb_id=room_id).select_related("objectdb").first()
        return profile.objectdb if profile else None
    return actor.location


def _no_room_message(kwargs: dict[str, Any]) -> str:
    return "No such room." if kwargs.get("room_id") else "You're not in a room."


def _no_exit_message(kwargs: dict[str, Any]) -> str:
    exit_name = (kwargs.get("exit") or "").strip()
    return f"No exit '{exit_name}' here." if exit_name else "No such exit here."


def _budget_suffix(room: ObjectDB) -> str:
    """``Space: used/total`` for the room's building — every structural reply carries it."""
    from world.buildings.room_services import building_for_room, space_used  # noqa: PLC0415

    building = building_for_room(room)
    if building is None:
        return ""
    return f" Space: {space_used(building)}/{building.space_budget}."


def _find_room_in_building(anchor: ObjectDB, name: str) -> ObjectDB | None:
    """Resolve a room by (display) name within the anchor room's building."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    try:
        area_id = anchor.room_profile.area_id
    except RoomProfile.DoesNotExist:
        return None
    profile = (
        RoomProfile.objects.filter(area_id=area_id, objectdb__db_key__iexact=name.strip())
        .select_related("objectdb")
        .first()
    )
    return profile.objectdb if profile else None


def _find_exit_in_room(room: ObjectDB, name: str) -> ObjectDB | None:
    return ObjectDB.objects.filter(
        db_typeclass_path="typeclasses.exits.Exit",
        db_location=room,
        db_key__iexact=name.strip(),
    ).first()


def _resolve_exit(room: ObjectDB, kwargs: dict[str, Any]) -> ObjectDB | None:
    """An exit in the anchor room, by explicit ``exit_id`` (web) or ``exit`` name (telnet)."""
    exit_id = kwargs.get("exit_id")
    if exit_id:
        return ObjectDB.objects.filter(
            pk=exit_id, db_typeclass_path="typeclasses.exits.Exit", db_location=room
        ).first()
    exit_name = (kwargs.get("exit") or "").strip()
    return _find_exit_in_room(room, exit_name) if exit_name else None


@dataclass
class _RoomBuilderAction(Action):
    """Shared shape for the owner-gated structural verbs (#670)."""

    category: str = "locations"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]


@dataclass
class DigRoomAction(_RoomBuilderAction):
    """Dig a stub room off the current room: direction + name, all else defaulted.

    Optional kwargs: ``description``, ``size`` (RoomSizeTier name), ``like``
    (name of an exemplar room in the building whose size/desc are copied).
    """

    key: str = "dig_room"
    name: str = "Dig Room"
    icon: str = "hammer"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia_extensions.models import RoomSizeTier  # noqa: PLC0415
        from world.buildings.room_services import RoomBuildError, dig_room  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        size = None
        size_name = (kwargs.get("size") or "").strip()
        if size_name:
            size = RoomSizeTier.objects.filter(name__iexact=size_name).first()
            if size is None:
                options = ", ".join(RoomSizeTier.objects.values_list("name", flat=True))
                return ActionResult(
                    success=False, message=f"No '{size_name}' size. Sizes: {options}."
                )
        like = None
        like_name = (kwargs.get("like") or "").strip()
        if like_name:
            like = _find_room_in_building(room, like_name)
            if like is None:
                return ActionResult(
                    success=False, message=f"No room named '{like_name}' in this building."
                )
        try:
            profile = dig_room(
                persona=_persona_for(actor),
                from_room=room,
                direction=kwargs.get("direction") or "",
                name=kwargs.get("name") or "",
                description=kwargs.get("description") or "",
                like=like,
                size=size,
            )
        except RoomBuildError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{profile.objectdb.db_key} dug.{_budget_suffix(room)}",
        )


@dataclass
class ResizeRoomAction(_RoomBuilderAction):
    """Change the size tier of the room you're standing in (instant, budget-checked)."""

    key: str = "resize_room"
    name: str = "Resize Room"
    icon: str = "expand"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia_extensions.models import RoomSizeTier  # noqa: PLC0415
        from world.buildings.room_services import RoomBuildError, resize_room  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        size_name = (kwargs.get("size") or "").strip()
        size = RoomSizeTier.objects.filter(name__iexact=size_name).first()
        if size is None:
            options = ", ".join(RoomSizeTier.objects.values_list("name", flat=True))
            return ActionResult(success=False, message=f"Pick a size: {options}.")
        try:
            resize_room(persona=_persona_for(actor), room=room, size=size)
        except RoomBuildError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"Room is now {size.name}.{_budget_suffix(room)}")


@dataclass
class RemoveRoomAction(_RoomBuilderAction):
    """Remove the room you're standing in (you and its contents move to the entry room)."""

    key: str = "remove_room"
    name: str = "Remove Room"
    icon: str = "trash"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.room_services import (  # noqa: PLC0415
            RoomBuildError,
            building_for_room,
            remove_room,
            space_used,
        )

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        building = building_for_room(room)
        try:
            remove_room(persona=_persona_for(actor), room=room)
        except RoomBuildError as exc:
            return ActionResult(success=False, message=exc.user_message)
        suffix = ""
        if building is not None:
            suffix = f" Space: {space_used(building)}/{building.space_budget}."
        return ActionResult(success=True, message=f"Room removed.{suffix}")


@dataclass
class LinkRoomsAction(_RoomBuilderAction):
    """Create a named exit pair between the current room and another room here.

    Kwargs: ``to`` (room name), ``name_there`` (exit name from here),
    ``name_back`` (exit name from there).
    """

    key: str = "link_rooms"
    name: str = "Link Rooms"
    icon: str = "link"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.room_services import RoomBuildError, link_rooms  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        to_name = (kwargs.get("to") or "").strip()
        to_room_id = kwargs.get("to_room_id")
        if to_room_id:
            other = _resolve_room(actor, {"room_id": to_room_id})
        else:
            other = _find_room_in_building(room, to_name) if to_name else None
        if other is None:
            return ActionResult(
                success=False, message=f"No room named '{to_name}' in this building."
            )
        try:
            link_rooms(
                persona=_persona_for(actor),
                room_a=room,
                room_b=other,
                name_ab=kwargs.get("name_there") or "",
                name_ba=kwargs.get("name_back") or "",
            )
        except RoomBuildError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"Linked to {other.db_key}.")


@dataclass
class UnlinkRoomsAction(_RoomBuilderAction):
    """Remove an exit (and its reverse) from the current room. Kwarg: ``exit``."""

    key: str = "unlink_rooms"
    name: str = "Unlink Rooms"
    icon: str = "unlink"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.room_services import RoomBuildError, unlink_rooms  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        exit_obj = _resolve_exit(room, kwargs)
        if exit_obj is None:
            return ActionResult(success=False, message=_no_exit_message(kwargs))
        try:
            unlink_rooms(persona=_persona_for(actor), exit_obj=exit_obj)
        except RoomBuildError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Exit removed.")


@dataclass
class RenameExitAction(_RoomBuilderAction):
    """Rename an exit in the current room. Kwargs: ``exit``, ``name``."""

    key: str = "rename_exit"
    name: str = "Rename Exit"
    icon: str = "pencil"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.room_services import RoomBuildError, rename_exit  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        exit_obj = _resolve_exit(room, kwargs)
        if exit_obj is None:
            return ActionResult(success=False, message=_no_exit_message(kwargs))
        try:
            rename_exit(
                persona=_persona_for(actor), exit_obj=exit_obj, name=kwargs.get("name") or ""
            )
        except RoomBuildError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Exit renamed.")


@dataclass
class PlaceRoomAction(_RoomBuilderAction):
    """Re-place a room on the building map grid (cosmetic; web canvas drag).

    Kwargs: ``room_id``, ``grid_x``, ``grid_y``, optional ``floor``.
    """

    key: str = "place_room"
    name: str = "Place Room"
    icon: str = "move"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.room_services import RoomBuildError, place_room  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        try:
            grid_x, grid_y = int(kwargs["grid_x"]), int(kwargs["grid_y"])
        except (KeyError, TypeError, ValueError):
            return ActionResult(success=False, message="Pick a spot on the map.")
        floor = kwargs.get("floor")
        try:
            place_room(
                persona=_persona_for(actor),
                room=room,
                grid_x=grid_x,
                grid_y=grid_y,
                floor=int(floor) if floor is not None else None,
            )
        except RoomBuildError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Room placed.")


@dataclass
class SetBuildingStyleAction(_RoomBuilderAction):
    """Dress the building in an architectural style. Kwargs: ``style``, optional ``room_id``.

    Default (living-realm) styles are open; throwback styles (#1469) require
    the codex knowledge their research projects grant (``can_build_style``).
    """

    key: str = "set_building_style"
    name: str = "Set Building Style"
    icon: str = "landmark"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.models import ArchitecturalStyle  # noqa: PLC0415
        from world.buildings.room_services import building_for_room  # noqa: PLC0415
        from world.buildings.services import (  # noqa: PLC0415
            can_build_style,
            set_building_style,
        )

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        building = building_for_room(room)
        if building is None:
            return ActionResult(success=False, message="This room isn't part of a building.")
        style_name = (kwargs.get("style") or "").strip()
        if not style_name:
            options = ", ".join(
                ArchitecturalStyle.objects.filter(is_active=True).values_list("name", flat=True)
            )
            return ActionResult(success=False, message=f"Pick a style: {options}.")
        style = ArchitecturalStyle.objects.filter(name__iexact=style_name).first()
        if style is None:
            return ActionResult(success=False, message=f"No style named '{style_name}'.")
        if not can_build_style(_persona_for(actor), style):
            return ActionResult(
                success=False,
                message=f"You haven't learned to build in the {style.name} style.",
            )
        set_building_style(building, style)
        return ActionResult(
            success=True, message=f"{building.area.name} is now built in the {style.name} style."
        )


@dataclass
class AssignRoomTenantAction(_RoomBuilderAction):
    """Owner grants a persona tenancy of the current room. Kwarg: ``tenant_persona_id``."""

    key: str = "assign_room_tenant"
    name: str = "Assign Tenant"
    icon: str = "user-plus"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.locations.services import RoomEditError, assign_room_tenant  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        tenant = Persona.objects.filter(pk=kwargs.get("tenant_persona_id")).first()
        if tenant is None:
            return ActionResult(success=False, message="No such persona.")
        try:
            assign_room_tenant(persona=_persona_for(actor), room=room, tenant_persona=tenant)
        except RoomEditError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"{tenant} is now a tenant here.")


@dataclass
class EndRoomTenancyAction(Action):
    """End a room tenancy (owner evicts, or the tenant departs). Kwarg: ``tenancy_id``."""

    key: str = "end_room_tenancy"
    name: str = "End Tenancy"
    icon: str = "user-minus"
    category: str = "locations"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.locations.models import LocationTenancy  # noqa: PLC0415
        from world.locations.services import RoomEditError, end_room_tenancy  # noqa: PLC0415

        tenancy = LocationTenancy.objects.filter(pk=kwargs.get("tenancy_id")).first()
        if tenancy is None:
            return ActionResult(success=False, message="No such tenancy.")
        try:
            end_room_tenancy(persona=_persona_for(actor), tenancy=tenancy)
        except RoomEditError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Tenancy ended.")


@dataclass
class SetPrimaryHomeAction(Action):
    """Make the room you're standing in your home (requires your active tenancy here)."""

    key: str = "set_primary_home"
    name: str = "Set Home"
    icon: str = "home"
    category: str = "locations"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomTenantPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.locations.services import RoomEditError, set_primary_home  # noqa: PLC0415

        room = actor.location
        if room is None:
            return ActionResult(success=False, message="You're not in a room.")
        try:
            set_primary_home(persona=_persona_for(actor), room=room)
        except RoomEditError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="This is home now.")


@dataclass
class CommissionDecorationAction(_RoomBuilderAction):
    """Commission a decoration ProjectTemplate. Kwargs: ``template_id``, ``target_room`` (bool).

    ``target_room=True`` decorates the room you're standing in; otherwise the
    whole building.
    """

    key: str = "commission_decoration"
    name: str = "Commission Decoration"
    icon: str = "paintbrush"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.models import ProjectTemplate  # noqa: PLC0415
        from world.buildings.room_services import (  # noqa: PLC0415
            RoomBuildError,
            building_for_room,
            commission_decoration,
        )

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        building = building_for_room(room)
        if building is None:
            return ActionResult(success=False, message="This room isn't part of a building.")
        template = ProjectTemplate.objects.filter(pk=kwargs.get("template_id")).first()
        if template is None:
            return ActionResult(success=False, message="No such decoration template.")
        try:
            project = commission_decoration(
                persona=_persona_for(actor),
                building=building,
                template=template,
                room=room if kwargs.get("target_room") else None,
            )
        except RoomBuildError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"'{template.name}' commissioned (project #{project.pk}).",
        )


@dataclass
class StartExtensionAction(_RoomBuilderAction):
    """Open a BUILDING_EXTENSION project for this building. Kwarg: ``added_budget``."""

    key: str = "start_building_extension"
    name: str = "Extend Building"
    icon: str = "plus-square"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.room_services import (  # noqa: PLC0415
            RoomBuildError,
            building_for_room,
            start_building_extension,
        )

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        building = building_for_room(room)
        if building is None:
            return ActionResult(success=False, message="This room isn't part of a building.")
        try:
            added = int(kwargs.get("added_budget") or 0)
        except (TypeError, ValueError):
            added = 0
        try:
            project = start_building_extension(
                persona=_persona_for(actor), building=building, added_budget=added
            )
        except RoomBuildError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"Extension project #{project.pk} opened (+{added} units on completion).",
        )
