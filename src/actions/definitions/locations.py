"""Player-facing room actions — the room-editor MVP seam (#1470) + the Room Builder (#670).

``RoomEditAction`` lets a room's **owner or tenant** edit the room they're
standing in (or targeting via ``room_id``): its display name, description, and
public/private listing (#2452 widened this from owner-only). It is the single
seam both telnet (``CmdManageRoom``) and the web (action-dispatch +
``RoomEditorPanel``) call. Owner-or-tenant standing is gated by
``IsRoomTenantPrerequisite``; the write + the public-toggle guard live in
``world.locations.services.set_room_display_data``.

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

_NOT_PART_OF_BUILDING_MESSAGE = "This room isn't part of a building."

if TYPE_CHECKING:
    from actions.types import ActionContext


@dataclass
class RoomEditAction(Action):
    """Owner or tenant edits the room they're standing in: name, description,
    public/private (#2452).

    Operates on ``actor.location`` (the room the actor is in), or the resolved
    ``room_id`` when the web canvas supplies one. Each field is optional — only
    those supplied are changed.
    """

    key: str = "edit_room"
    name: str = "Edit Room"
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
            return ActionResult(success=False, message=_NOT_PART_OF_BUILDING_MESSAGE)
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
    """Make the room you're standing in your home (requires owner or tenant standing here)."""

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
class TagRoomResonanceAction(Action):
    """Tag the room you're standing in with a resonance you've claimed (#2036).

    Thin wrapper over ``world.magic.services.gain.tag_room_resonance`` — the
    already-idempotent room-aura cascade write. Gated on owner-or-tenant
    standing (``IsRoomTenantPrerequisite``, widened #2036) rather than a
    direct tenancy row, so an owner with no personal ``LocationTenancy`` can
    still dress their own room. The claimed-resonance check mirrors the same
    predicate the pose/scene-entry endorsement services use — you can only
    tag with a resonance already on your own sheet.
    """

    key: str = "tag_room_resonance"
    name: str = "Tag Room Aura"
    icon: str = "sparkles"
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
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.magic.models import Resonance  # noqa: PLC0415
        from world.magic.services.gain import tag_room_resonance  # noqa: PLC0415

        room = actor.location
        if room is None:
            return ActionResult(success=False, message="You're not in a room.")
        resonance = Resonance.objects.filter(pk=kwargs.get("resonance_id")).first()
        if resonance is None:
            return ActionResult(success=False, message="No such resonance.")
        sheet = actor.sheet_data
        if not sheet.resonances.filter(resonance=resonance).exists():
            return ActionResult(success=False, message="You haven't claimed that resonance.")
        try:
            profile = room.room_profile
        except RoomProfile.DoesNotExist:
            return ActionResult(success=False, message="This room can't hold a resonance aura.")
        tag_room_resonance(profile, resonance)
        return ActionResult(success=True, message=f"You tag this room with {resonance.name}.")


@dataclass
class UntagRoomResonanceAction(Action):
    """Remove a resonance tag from the room you're standing in (#2036).

    Mirrors ``TagRoomResonanceAction`` over ``untag_room_resonance``, same
    owner-or-tenant gate. No claimed-resonance check on removal — untagging
    something you can no longer claim is still a valid "undo."
    """

    key: str = "untag_room_resonance"
    name: str = "Untag Room Aura"
    icon: str = "sparkles"
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
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.magic.models import Resonance  # noqa: PLC0415
        from world.magic.services.gain import untag_room_resonance  # noqa: PLC0415

        room = actor.location
        if room is None:
            return ActionResult(success=False, message="You're not in a room.")
        resonance = Resonance.objects.filter(pk=kwargs.get("resonance_id")).first()
        if resonance is None:
            return ActionResult(success=False, message="No such resonance.")
        try:
            profile = room.room_profile
        except RoomProfile.DoesNotExist:
            return ActionResult(success=False, message="This room can't hold a resonance aura.")
        untag_room_resonance(profile, resonance)
        return ActionResult(success=True, message=f"You untag {resonance.name} from this room.")


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
            return ActionResult(success=False, message=_NOT_PART_OF_BUILDING_MESSAGE)
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
            return ActionResult(success=False, message=_NOT_PART_OF_BUILDING_MESSAGE)
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


@dataclass
class PlaceFixtureAction(_RoomBuilderAction):
    """Place a comfort fixture in a room. Kwargs: ``kind``, optional ``room_id``.

    Fixtures are the build-to-win mitigation tools (#1514): stackable,
    presence-only (no toggle — a hearth is always lit), instant and free
    (cost is the economy pass's knob).
    """

    key: str = "place_room_fixture"
    name: str = "Place Fixture"
    icon: str = "flame"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.buildings.models import DecorationKind  # noqa: PLC0415
        from world.buildings.services import place_decoration  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        kind_name = (kwargs.get("kind") or "").strip()
        kind = DecorationKind.objects.filter(name__iexact=kind_name).first() if kind_name else None
        if kind is None:
            options = ", ".join(DecorationKind.objects.values_list("name", flat=True))
            return ActionResult(success=False, message=f"Pick a fixture: {options}.")
        try:
            profile = room.room_profile
        except RoomProfile.DoesNotExist:
            return ActionResult(success=False, message="This room can't hold fixtures.")
        place_decoration(profile, kind)
        return ActionResult(success=True, message=f"{kind.name} placed.")


@dataclass
class RemoveFixtureAction(_RoomBuilderAction):
    """Remove a placed comfort fixture. Kwargs: ``kind``, optional ``room_id``."""

    key: str = "remove_room_fixture"
    name: str = "Remove Fixture"
    icon: str = "flame-kindling"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.models import RoomDecoration  # noqa: PLC0415
        from world.buildings.services import remove_decoration  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        kind_name = (kwargs.get("kind") or "").strip()
        decoration = (
            RoomDecoration.objects.filter(room_profile__objectdb=room, kind__name__iexact=kind_name)
            .order_by("-placed_at")
            .first()
            if kind_name
            else None
        )
        if decoration is None:
            return ActionResult(success=False, message=f"No '{kind_name}' fixture here.")
        name = decoration.kind.name
        remove_decoration(decoration)
        return ActionResult(success=True, message=f"{name} removed.")


def _kind_flags(kind: Any) -> str:
    """Bracketed comma-joined short-names of a ``BuildingKind``'s active flags.

    Display-only — the glossary says the flags carry no mechanical weight, so a
    model method would imply otherwise.
    """
    _NAMES = (
        ("is_residential", "residential"),
        ("is_commercial", "commercial"),
        ("is_fortified", "fortified"),
        ("is_occult", "occult"),
        ("is_maritime", "maritime"),
        ("is_agrarian", "agrarian"),
        ("is_aerial", "aerial"),
        ("is_subterranean", "subterranean"),
        ("is_secret", "secret"),
    )
    active = [label for field, label in _NAMES if getattr(kind, field)]
    return f" [{', '.join(active)}]" if active else ""


@dataclass
class StartBuildingRenovationAction(_RoomBuilderAction):
    """Commission a funded renovation re-pointing the building to a new kind.

    Kwargs: ``target_kind`` (str — name or pk), optional ``room_id`` (web canvas).
    Bare invocation lists all ``BuildingKind`` rows excluding the building's
    current kind.
    """

    key: str = "start_building_renovation"
    name: str = "Renovate Building"
    icon: str = "hammer"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.models import BuildingKind  # noqa: PLC0415
        from world.buildings.renovation_services import (  # noqa: PLC0415
            start_building_renovation,
        )
        from world.buildings.room_services import (  # noqa: PLC0415
            RoomBuildError,
            building_for_room,
        )

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        building = building_for_room(room)
        if building is None:
            return ActionResult(success=False, message=_NOT_PART_OF_BUILDING_MESSAGE)
        target = (kwargs.get("target_kind") or "").strip()
        if not target:
            lines = [
                f"{kind.name}{_kind_flags(kind)}"
                for kind in BuildingKind.objects.exclude(pk=building.kind_id)
            ]
            return ActionResult(success=False, message="Renovate to: " + ", ".join(lines))
        kind = (
            BuildingKind.objects.get(pk=target)
            if target.isdigit()
            else BuildingKind.objects.filter(name__iexact=target).first()
        )
        if kind is None:
            return ActionResult(success=False, message=f"No building kind named '{target}'.")
        try:
            project = start_building_renovation(
                persona=_persona_for(actor), building=building, target_kind=kind
            )
        except RoomBuildError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"'{kind.name}' renovation commissioned (project #{project.pk}).",
        )


@dataclass
class StartBuildingActivationAction(_RoomBuilderAction):
    """Commission the project bringing a granted building to life.

    Distinct from ``start_building_renovation`` (kind-swap) and
    ``refurbish_building`` (priced instant recovery, refused on an
    un-activated granted building) — this is the one-time commissioning
    step for a granted building's activation arc.
    """

    key: str = "start_building_activation"
    name: str = "Activate Property Grant"
    icon: str = "hammer"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.property_grant_services import (  # noqa: PLC0415
            start_building_activation,
        )
        from world.buildings.room_services import RoomBuildError, building_for_room  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))
        building = building_for_room(room)
        if building is None:
            return ActionResult(success=False, message=_NOT_PART_OF_BUILDING_MESSAGE)
        try:
            project = start_building_activation(persona=_persona_for(actor), building=building)
        except RoomBuildError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"Activation commissioned (project #{project.pk}). Fund it via project/donate.",
        )


def _building_condition_status(building) -> str:
    """Owner-only condition/upkeep readout (#1930).

    The public renown payload carries only the fiction label; exact
    arrears / miss counts / ultra state surface here, on the owner's own
    actions.
    """
    from world.buildings.upkeep_services import building_weekly_upkeep  # noqa: PLC0415

    parts = [
        f"Condition: {building.get_condition_tier_display()}.",
        f"Weekly upkeep: {building_weekly_upkeep(building)} coppers.",
    ]
    if building.upkeep_arrears:
        parts.append(f"Arrears owed: {building.upkeep_arrears} coppers.")
    if building.consecutive_missed_upkeep:
        parts.append(f"Missed weeks: {building.consecutive_missed_upkeep}.")
    if building.ultra_upkeep:
        parts.append("Ultra upkeep: ON.")
    if building.mothballed_at is not None:
        parts.append("Mothballed (hidden; upkeep frozen).")
    return " ".join(parts)


def _resolve_building_and_purse(actor: ObjectDB, kwargs: dict[str, Any]):
    """Shared resolution for the condition action family (#1930).

    Returns ``(building, purse, error_result)`` — exactly one of
    building/error_result is set; purse accompanies a resolved building.
    """
    from world.buildings.room_services import building_for_room  # noqa: PLC0415
    from world.currency.services import get_or_create_purse  # noqa: PLC0415

    room = _resolve_room(actor, kwargs)
    if room is None:
        return None, None, ActionResult(success=False, message=_no_room_message(kwargs))
    building = building_for_room(room)
    if building is None:
        return (
            None,
            None,
            ActionResult(success=False, message="This room isn't part of a building."),
        )
    persona = _persona_for(actor)
    purse = get_or_create_purse(persona.character_sheet)
    return building, purse, None


@dataclass
class SettleBuildingArrearsAction(_RoomBuilderAction):
    """Pay off the building's accrued upkeep arrears (#1930).

    Bare invocation shows the owner-only condition/arrears status; pass
    ``confirm`` to pay. Kwargs: optional ``room_id`` (web canvas),
    optional ``confirm``.
    """

    key: str = "settle_building_arrears"
    name: str = "Settle Upkeep Arrears"
    icon: str = "coins"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.buildings.condition_services import settle_upkeep_arrears  # noqa: PLC0415

        building, purse, error = _resolve_building_and_purse(actor, kwargs)
        if error is not None:
            return error
        if not kwargs.get("confirm"):
            status = _building_condition_status(building)
            return ActionResult(success=False, message=f"{status} Confirm to settle.")
        try:
            paid = settle_upkeep_arrears(building=building, payer_purse=purse)
        except ValidationError as exc:
            return ActionResult(success=False, message=exc.messages[0])
        if paid == 0:
            return ActionResult(success=True, message="Nothing is owed on this building.")
        return ActionResult(success=True, message=f"You settle {paid} coppers of back upkeep.")


@dataclass
class RefurbishBuildingAction(_RoomBuilderAction):
    """Restore the building's condition to Excellent for coppers (#1930).

    Distinct from the ``start_building_renovation`` kind-swap project —
    refurbishment is the priced condition restore. Bare invocation quotes
    the cost; pass ``confirm`` to pay. Kwargs: optional ``room_id``,
    optional ``confirm``.
    """

    key: str = "refurbish_building"
    name: str = "Refurbish Building"
    icon: str = "paint-roller"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.buildings.condition_services import (  # noqa: PLC0415
            ConditionServiceError,
            refurbish_building,
            refurbish_cost,
        )

        building, purse, error = _resolve_building_and_purse(actor, kwargs)
        if error is not None:
            return error
        if not kwargs.get("confirm"):
            status = _building_condition_status(building)
            cost = refurbish_cost(building)
            return ActionResult(
                success=False,
                message=f"{status} Refurbishing to Excellent costs {cost} coppers. "
                "Confirm to proceed.",
            )
        try:
            cost = refurbish_building(building=building, payer_purse=purse)
        except ConditionServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValidationError as exc:
            return ActionResult(success=False, message=exc.messages[0])
        return ActionResult(
            success=True,
            message=f"Craftsmen sweep through for {cost} coppers — the building is "
            "restored to excellent condition.",
        )


@dataclass
class PrepareBuildingAction(_RoomBuilderAction):
    """Grand preparation: commission the cleanup project pushing above normal (#1930).

    The party-preparation loop — each project pushes one tier above
    Excellent (then Immaculate) for a temporary prestige kick that decays
    back within about a week. The cost is a proportion of the house's
    prestige; the commissioned project is funded with coppers
    (``project/donate``) and sped along with AP Household Command checks
    (``project/check``). Bare invocation quotes the cost; pass ``confirm``
    to commission. Kwargs: optional ``room_id``, optional ``confirm``.
    """

    key: str = "prepare_building"
    name: str = "Grand Preparation"
    icon: str = "sparkles"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.condition_services import (  # noqa: PLC0415
            ConditionServiceError,
            prepare_cost,
            start_building_preparation,
        )

        building, _purse, error = _resolve_building_and_purse(actor, kwargs)
        if error is not None:
            return error
        if not kwargs.get("confirm"):
            status = _building_condition_status(building)
            try:
                cost = prepare_cost(building)
            except ConditionServiceError as exc:
                return ActionResult(success=False, message=f"{status} {exc.user_message}")
            return ActionResult(
                success=False,
                message=f"{status} A grand preparation will take {cost} coppers of funding. "
                "Confirm to commission the project.",
            )
        try:
            project = start_building_preparation(building=building, persona=_persona_for(actor))
        except ConditionServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"The household begins the grand preparation (project #{project.pk}). "
            f"Fund it with 'project/donate {project.pk}=<coppers>' or lend a hand with "
            f"'project/check {project.pk}=Direct the Household'.",
        )


@dataclass
class ToggleUltraUpkeepAction(_RoomBuilderAction):
    """Toggle the ultra-upkeep premium that holds Immaculate condition (#1930).

    While on (and affordable), the weekly sweep charges an outrageous
    premium on top of normal upkeep to keep the building Immaculate past
    its dwell. Kwargs: optional ``room_id``.
    """

    key: str = "toggle_ultra_upkeep"
    name: str = "Ultra Upkeep"
    icon: str = "gem"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.condition_services import set_ultra_upkeep  # noqa: PLC0415
        from world.buildings.constants import ULTRA_UPKEEP_MULTIPLIER  # noqa: PLC0415
        from world.buildings.upkeep_services import building_weekly_upkeep  # noqa: PLC0415

        building, _purse, error = _resolve_building_and_purse(actor, kwargs)
        if error is not None:
            return error
        enabled = not building.ultra_upkeep
        set_ultra_upkeep(building=building, enabled=enabled)
        if enabled:
            premium = ULTRA_UPKEEP_MULTIPLIER * building_weekly_upkeep(building)
            return ActionResult(
                success=True,
                message=f"Ultra upkeep engaged — {premium} coppers per week on top of "
                "normal upkeep while the building is Immaculate.",
            )
        return ActionResult(success=True, message="Ultra upkeep discontinued.")
