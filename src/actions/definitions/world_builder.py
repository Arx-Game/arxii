"""Staff world-builder actions (#2449) — the canvas's dispatch seam.

Seventeen REGISTRY actions (eleven original + six discovery/portal-authoring, #2451),
all ``category="world_builder"``, ``target_type=SELF``,
gated by ``StaffOnlyPrerequisite`` alone (no ownership/tenancy standing — this is
staff tooling, not a player-facing builder). Each is a thin wrapper over the
Task 1+2 substrate: ``world.areas.grid_services`` (room/exit/grid primitives +
``promote_to_authored``/``suggest_fixture_key``) and
``world.locations.services.set_room_display_data(..., bypass_ownership=True)``.

Unlike the owner-facing Room Builder (``locations.py``), there is no "anchor
room" (``actor.location``) fallback — every id kwarg (``area_id``/``room_id``/
``exit_id``/etc.) is resolved explicitly inside ``execute()``, since REST
dispatch passes raw ints and staff building happens over the whole shared map,
not from the actor's own position (#2163).

``staff_dig_room`` requires an AUTHORED area (canonical world rooms only — a
STORY/PLAYER area is out of scope for this canvas). ``staff_remove_room``
refuses an already-exported room (``fixture_key`` set + ``origin=AUTHORED``):
those come out via the report-never-delete pipeline (see
``core_management.content_export``), never the canvas. ``staff_unlink_rooms``'s
stranding guard is deliberately looser than the building Room Builder's
BFS-reachability check (which has no meaningful "anchor room" world-wide) — it
only refuses when the drop would leave an occupied room with zero exits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import Prerequisite, StaffOnlyPrerequisite
from actions.types import ActionResult, TargetType

# Shared error messages.
_NO_SUCH_AREA = "No such area."
_NO_SUCH_ROOM_MSG = "No such room."

if TYPE_CHECKING:
    from actions.types import ActionContext
    from evennia_extensions.models import RoomProfile
    from world.areas.models import Area
    from world.clues.models import ClueTrigger, RoomClue
    from world.magic.models import PortalAnchor

_EXIT_TYPECLASS = "typeclasses.exits.Exit"


def _resolve_area(area_id: Any) -> Area | None:
    from world.areas.models import Area  # noqa: PLC0415

    if not area_id:
        return None
    return Area.objects.filter(pk=area_id).first()


def _resolve_room_profile(room_id: Any) -> RoomProfile | None:
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    if not room_id:
        return None
    return (
        RoomProfile.objects.filter(objectdb_id=room_id).select_related("objectdb", "area").first()
    )


def _resolve_room_clue(room_clue_id: Any) -> RoomClue | None:
    from world.clues.models import RoomClue  # noqa: PLC0415

    if not room_clue_id:
        return None
    return RoomClue.objects.filter(pk=room_clue_id).select_related("room_profile", "clue").first()


def _resolve_clue_trigger(clue_trigger_id: Any) -> ClueTrigger | None:
    from world.clues.models import ClueTrigger  # noqa: PLC0415

    if not clue_trigger_id:
        return None
    return (
        ClueTrigger.objects.filter(pk=clue_trigger_id)
        .select_related("room_profile", "clue")
        .first()
    )


def _resolve_portal_anchor(anchor_id: Any) -> PortalAnchor | None:
    from world.magic.models import PortalAnchor  # noqa: PLC0415

    if not anchor_id:
        return None
    return PortalAnchor.objects.active().filter(pk=anchor_id).select_related("room_profile").first()


def _resolve_exit(exit_id: Any) -> ObjectDB | None:
    if not exit_id:
        return None
    return ObjectDB.objects.filter(pk=exit_id, db_typeclass_path=_EXIT_TYPECLASS).first()


def _exit_pair(exit_obj: ObjectDB) -> list[ObjectDB]:
    """The exit and its reverse-direction sibling (if one exists)."""
    pair = [exit_obj]
    reverse = ObjectDB.objects.filter(
        db_typeclass_path=_EXIT_TYPECLASS,
        db_location=exit_obj.db_destination,
        db_destination=exit_obj.db_location,
    ).first()
    if reverse is not None:
        pair.append(reverse)
    return pair


def _resolve_authored_area(area_id: Any) -> tuple[Area | None, str | None]:
    """Resolve ``area_id`` to an AUTHORED area, or an error message.

    Collapses "no such area" and "area isn't AUTHORED yet" into one call so
    ``StaffDigRoomAction.execute`` doesn't need two separate early returns
    for what's really one precondition (stays under the return-count lint).
    """
    from world.areas.constants import GridOrigin  # noqa: PLC0415

    area = _resolve_area(area_id)
    if area is None:
        return None, _NO_SUCH_AREA
    if area.origin != GridOrigin.AUTHORED:
        return None, "This area must be AUTHORED before rooms can be dug into it."
    return area, None


def _parse_dig_room_grid(kwargs: dict[str, Any]) -> tuple[int | None, int | None, int] | None:
    """Parse ``grid_x``/``grid_y``/``floor`` ints out of ``kwargs``.

    Returns ``None`` on any malformed value instead of letting ``int()`` raise
    past ``execute()`` into an unhandled exception (#2449 review finding).
    """
    grid_x_raw = kwargs.get("grid_x")
    grid_y_raw = kwargs.get("grid_y")
    try:
        grid_x = int(grid_x_raw) if grid_x_raw is not None else None
        grid_y = int(grid_y_raw) if grid_y_raw is not None else None
        floor = int(kwargs.get("floor") or 0)
    except (KeyError, TypeError, ValueError):
        return None
    return grid_x, grid_y, floor


def _stranded_occupied_room(rooms: set[ObjectDB], dropped_exit_ids: set[int]) -> ObjectDB | None:
    """The first room in ``rooms`` that would be left exit-less AND occupied."""
    from world.areas.grid_services import has_character_occupants  # noqa: PLC0415

    for room in rooms:
        if room is None:
            # A dangling one-way exit can have a null db_location/db_destination
            # (nullable FKs) — nothing to strand there.
            continue
        remaining = (
            ObjectDB.objects.filter(db_typeclass_path=_EXIT_TYPECLASS, db_location=room)
            .exclude(pk__in=dropped_exit_ids)
            .exists()
        )
        if not remaining and has_character_occupants(room):
            return room
    return None


@dataclass
class _WorldBuilderAction(Action):
    """Shared shape for the staff world-builder canvas verbs (#2449)."""

    category: str = "world_builder"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [StaffOnlyPrerequisite()]


@dataclass
class CreateAreaAction(_WorldBuilderAction):
    """Create a new AUTHORED area.

    Kwargs: ``name``, ``slug``, ``level`` (int), optional ``parent_id``.
    """

    key: str = "create_area"
    name: str = "Create Area"
    icon: str = "map"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.areas.constants import GridOrigin  # noqa: PLC0415
        from world.areas.models import Area  # noqa: PLC0415

        area_name = (kwargs.get("name") or "").strip()
        slug = (kwargs.get("slug") or "").strip()
        if not area_name or not slug:
            return ActionResult(success=False, message="An area needs both a name and a slug.")
        try:
            level = int(kwargs["level"])
        except (KeyError, TypeError, ValueError):
            return ActionResult(success=False, message="Pick a level.")
        parent_id = kwargs.get("parent_id")
        parent = _resolve_area(parent_id)
        if parent_id and parent is None:
            return ActionResult(success=False, message="No such parent area.")
        area = Area(
            name=area_name,
            slug=slug,
            level=level,
            parent=parent,
            origin=GridOrigin.AUTHORED,
        )
        try:
            area.save()
        except ValidationError as exc:
            return ActionResult(success=False, message="; ".join(exc.messages))
        return ActionResult(success=True, message=f"{area.name} created (area #{area.pk}).")


@dataclass
class EditAreaAction(_WorldBuilderAction):
    """Edit an area. Kwargs: ``area_id``, optional ``name``/``slug``/``level``/``parent_id``.

    A slug change on an already-keyed area is refused — keys are permanent
    once set (shares ``ensure_slug_change_allowed`` with
    ``promote_to_authored``'s guard).
    """

    key: str = "edit_area"
    name: str = "Edit Area"
    icon: str = "map"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.areas.grid_services import ensure_slug_change_allowed  # noqa: PLC0415

        area = _resolve_area(kwargs.get("area_id"))
        if area is None:
            return ActionResult(success=False, message=_NO_SUCH_AREA)
        new_slug = kwargs.get("slug")
        refusal = ensure_slug_change_allowed(area, new_slug)
        if refusal is not None:
            return ActionResult(success=False, message=refusal)
        if kwargs.get("name") is not None:
            area.name = kwargs["name"]
        if new_slug is not None:
            area.slug = new_slug
        if kwargs.get("level") is not None:
            try:
                area.level = int(kwargs["level"])
            except (TypeError, ValueError):
                return ActionResult(success=False, message="Pick a valid level.")
        parent_id = kwargs.get("parent_id")
        if parent_id is not None:
            parent = _resolve_area(parent_id)
            if parent is None:
                return ActionResult(success=False, message="No such parent area.")
            area.parent = parent
        try:
            area.save()
        except ValidationError as exc:
            return ActionResult(success=False, message="; ".join(exc.messages))
        return ActionResult(success=True, message=f"{area.name} updated.")


@dataclass
class StaffDigRoomAction(_WorldBuilderAction):
    """Dig a room into an AUTHORED area — no exit requirement (linking is separate).

    Kwargs: ``area_id``, ``name``, optional ``description``/``size``/``grid_x``/
    ``grid_y``/``floor``/``fixture_key`` (defaults to ``suggest_fixture_key``).
    """

    key: str = "staff_dig_room"
    name: str = "Dig World Room"
    icon: str = "hammer"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia_extensions.models import RoomSizeTier  # noqa: PLC0415
        from world.areas.constants import GridOrigin  # noqa: PLC0415
        from world.areas.grid_services import (  # noqa: PLC0415
            GridServiceError,
            cell_occupied,
            create_room,
            suggest_fixture_key,
        )

        area, area_error = _resolve_authored_area(kwargs.get("area_id"))
        if area_error is not None:
            return ActionResult(success=False, message=area_error)
        room_name = (kwargs.get("name") or "").strip()
        if not room_name:
            return ActionResult(success=False, message="Name the room.")
        size = None
        size_name = (kwargs.get("size") or "").strip()
        if size_name:
            size = RoomSizeTier.objects.filter(name__iexact=size_name).first()
            if size is None:
                options = ", ".join(RoomSizeTier.objects.values_list("name", flat=True))
                return ActionResult(
                    success=False, message=f"No '{size_name}' size. Sizes: {options}."
                )
        fixture_key = kwargs.get("fixture_key")
        if not fixture_key:
            try:
                fixture_key = suggest_fixture_key(area, room_name)
            except GridServiceError as exc:
                return ActionResult(success=False, message=exc.user_message)
        parsed_grid = _parse_dig_room_grid(kwargs)
        if parsed_grid is None:
            return ActionResult(success=False, message="Grid position and floor must be numbers.")
        grid_x, grid_y, floor = parsed_grid
        unplaced_note = ""
        if grid_x is not None and grid_y is not None and cell_occupied(area, grid_x, grid_y, floor):
            # Cosmetic coordinates never block creation (mirrors dig_room's
            # precedent) — place_room_on_grid is the verb that still raises.
            grid_x = None
            grid_y = None
            unplaced_note = (
                " That cell was occupied — room created unplaced; drag it into position."
            )
        profile = create_room(
            area=area,
            name=room_name,
            description=kwargs.get("description") or "",
            size=size,
            grid_x=grid_x,
            grid_y=grid_y,
            floor=floor,
            origin=GridOrigin.AUTHORED,
            fixture_key=fixture_key,
        )
        return ActionResult(
            success=True,
            message=f"{profile.objectdb.db_key} dug (#{profile.pk}).{unplaced_note}",
        )


@dataclass
class StaffEditRoomAction(_WorldBuilderAction):
    """Edit a world room's display data + profile flags.

    Kwargs: ``room_id``, optional ``name``/``description``/``is_public``/
    ``is_social_hub``/``is_outdoor``/``enclosure``.
    """

    key: str = "staff_edit_room"
    name: str = "Edit World Room"
    icon: str = "pencil"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia_extensions.constants import RoomEnclosure  # noqa: PLC0415
        from world.locations.services import RoomEditError, set_room_display_data  # noqa: PLC0415

        profile = _resolve_room_profile(kwargs.get("room_id"))
        if profile is None:
            return ActionResult(success=False, message=_NO_SUCH_ROOM_MSG)
        display_name = kwargs.get("name")
        description = kwargs.get("description")
        is_public = kwargs.get("is_public")
        if display_name is not None or description is not None or is_public is not None:
            try:
                set_room_display_data(
                    room=profile.objectdb,
                    persona=None,
                    name=display_name,
                    description=description,
                    is_public=is_public,
                    bypass_ownership=True,
                )
            except RoomEditError as exc:
                return ActionResult(success=False, message=exc.user_message)
        update_fields = []
        if kwargs.get("is_social_hub") is not None:
            profile.is_social_hub = bool(kwargs["is_social_hub"])
            update_fields.append("is_social_hub")
        if kwargs.get("is_outdoor") is not None:
            profile.is_outdoor = bool(kwargs["is_outdoor"])
            update_fields.append("is_outdoor")
        enclosure = kwargs.get("enclosure")
        if enclosure:
            valid = {choice for choice, _ in RoomEnclosure.choices}
            if enclosure not in valid:
                options = ", ".join(sorted(valid))
                return ActionResult(success=False, message=f"Pick an enclosure: {options}.")
            profile.enclosure = enclosure
            update_fields.append("enclosure")
        if update_fields:
            profile.save(update_fields=update_fields)
        return ActionResult(success=True, message=f"{profile.objectdb.db_key} updated.")


@dataclass
class StaffLinkRoomsAction(_WorldBuilderAction):
    """Link two world rooms with a named exit pair — cross-area allowed.

    Kwargs: ``room_a_id``, ``room_b_id``, ``name_ab``, ``name_ba``.
    """

    key: str = "staff_link_rooms"
    name: str = "Link World Rooms"
    icon: str = "link"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.areas.grid_services import create_exit_pair  # noqa: PLC0415

        room_a = _resolve_room_profile(kwargs.get("room_a_id"))
        room_b = _resolve_room_profile(kwargs.get("room_b_id"))
        if room_a is None or room_b is None:
            return ActionResult(success=False, message=_NO_SUCH_ROOM_MSG)
        name_ab = (kwargs.get("name_ab") or "").strip()
        name_ba = (kwargs.get("name_ba") or "").strip()
        if not name_ab or not name_ba:
            return ActionResult(
                success=False, message="Both exit names are needed (one for each direction)."
            )
        create_exit_pair(
            name=name_ab,
            aliases=(),
            reverse_name=name_ba,
            reverse_aliases=(),
            room_a=room_a.objectdb,
            room_b=room_b.objectdb,
        )
        return ActionResult(
            success=True,
            message=f"Linked {room_a.objectdb.db_key} <-> {room_b.objectdb.db_key}.",
        )


@dataclass
class StaffUnlinkRoomsAction(_WorldBuilderAction):
    """Remove an exit and its reverse sibling. Kwarg: ``exit_id``.

    Refuses only when the removal would leave an occupied room with zero
    remaining exits (a world-wide BFS-reachability guard, like the building
    Room Builder's, has no meaningful anchor room here).
    """

    key: str = "staff_unlink_rooms"
    name: str = "Unlink World Rooms"
    icon: str = "unlink"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        exit_obj = _resolve_exit(kwargs.get("exit_id"))
        if exit_obj is None:
            return ActionResult(success=False, message="No such exit.")
        pair = _exit_pair(exit_obj)
        rooms = {exit_obj.db_location, exit_obj.db_destination}
        stranded = _stranded_occupied_room(rooms, {e.pk for e in pair})
        if stranded is not None:
            return ActionResult(
                success=False,
                message=f"Removing that exit would strand {stranded.db_key}, which has "
                "characters in it.",
            )
        for e in pair:
            e.delete()
        return ActionResult(success=True, message="Exit removed.")


@dataclass
class StaffRenameExitAction(_WorldBuilderAction):
    """Rename one direction of an exit. Kwargs: ``exit_id``, ``name``."""

    key: str = "staff_rename_exit"
    name: str = "Rename World Exit"
    icon: str = "pencil"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        exit_obj = _resolve_exit(kwargs.get("exit_id"))
        if exit_obj is None:
            return ActionResult(success=False, message="No such exit.")
        new_name = (kwargs.get("name") or "").strip()
        if not new_name:
            return ActionResult(success=False, message="The exit needs a name.")
        exit_obj.db_key = new_name
        exit_obj.save(update_fields=["db_key"])
        return ActionResult(success=True, message=f"Exit renamed to {new_name}.")


@dataclass
class StaffPlaceRoomAction(_WorldBuilderAction):
    """Place a world room on its area's map grid (cosmetic; canvas drag).

    Kwargs: ``room_id``, ``grid_x``, ``grid_y``, optional ``floor``.
    """

    key: str = "staff_place_room"
    name: str = "Place World Room"
    icon: str = "move"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.areas.grid_services import GridServiceError, place_room_on_grid  # noqa: PLC0415

        profile = _resolve_room_profile(kwargs.get("room_id"))
        if profile is None:
            return ActionResult(success=False, message=_NO_SUCH_ROOM_MSG)
        try:
            grid_x, grid_y = int(kwargs["grid_x"]), int(kwargs["grid_y"])
        except (KeyError, TypeError, ValueError):
            return ActionResult(success=False, message="Pick a spot on the map.")
        floor = kwargs.get("floor")
        try:
            place_room_on_grid(
                profile=profile,
                grid_x=grid_x,
                grid_y=grid_y,
                floor=int(floor) if floor is not None else profile.floor,
            )
        except GridServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Room placed.")


@dataclass
class StaffRemoveRoomAction(_WorldBuilderAction):
    """Remove a world room. Kwarg: ``room_id``.

    Refuses when the room has any contents (characters or items — empty it
    first, so an item is never silently orphaned with ``db_location=NULL``),
    when it has an installed ``RoomFeatureInstance``, or when it's already
    exported (``fixture_key`` set + ``origin=AUTHORED`` — those come out via
    the report-never-delete pipeline, not the canvas). Else deletes exits
    pointing in/out, then the room itself, atomically.
    """

    key: str = "staff_remove_room"
    name: str = "Remove World Room"
    icon: str = "trash"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.db import transaction  # noqa: PLC0415

        from world.areas.constants import GridOrigin  # noqa: PLC0415
        from world.areas.grid_services import has_non_exit_contents  # noqa: PLC0415
        from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

        profile = _resolve_room_profile(kwargs.get("room_id"))
        if profile is None:
            return ActionResult(success=False, message=_NO_SUCH_ROOM_MSG)
        room = profile.objectdb
        if has_non_exit_contents(room):
            return ActionResult(success=False, message="This room isn't empty; empty it first.")
        if RoomFeatureInstance.objects.filter(room_profile=profile).active().exists():
            return ActionResult(
                success=False, message="This room has an installed feature; remove that first."
            )
        if profile.fixture_key is not None and profile.origin == GridOrigin.AUTHORED:
            return ActionResult(
                success=False,
                message="Exported rooms are removed via the report-never-delete pipeline, "
                "not the canvas.",
            )
        with transaction.atomic():
            ObjectDB.objects.filter(db_typeclass_path=_EXIT_TYPECLASS, db_location=room).delete()
            ObjectDB.objects.filter(db_typeclass_path=_EXIT_TYPECLASS, db_destination=room).delete()
            room.delete()
        return ActionResult(success=True, message="Room removed.")


@dataclass
class PromoteRoomAction(_WorldBuilderAction):
    """Promote a room to AUTHORED. Kwargs: ``room_id``, optional ``fixture_key`` (suggested)."""

    key: str = "promote_room"
    name: str = "Promote Room"
    icon: str = "star"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.areas.grid_services import (  # noqa: PLC0415
            GridServiceError,
            promote_to_authored,
            suggest_fixture_key,
        )

        profile = _resolve_room_profile(kwargs.get("room_id"))
        if profile is None:
            return ActionResult(success=False, message=_NO_SUCH_ROOM_MSG)
        fixture_key = kwargs.get("fixture_key")
        if not fixture_key:
            if profile.area is None:
                return ActionResult(success=False, message="This room has no area to promote into.")
            try:
                fixture_key = suggest_fixture_key(profile.area, profile.objectdb.db_key)
            except GridServiceError as exc:
                return ActionResult(success=False, message=exc.user_message)
        try:
            promote_to_authored(room_profile=profile, key=fixture_key)
        except GridServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True, message=f"{profile.objectdb.db_key} promoted as {fixture_key}."
        )


@dataclass
class PromoteAreaAction(_WorldBuilderAction):
    """Promote an area to AUTHORED. Kwargs: ``area_id``, optional ``slug`` (slugified name)."""

    key: str = "promote_area"
    name: str = "Promote Area"
    icon: str = "star"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.utils.text import slugify  # noqa: PLC0415

        from world.areas.grid_services import GridServiceError, promote_to_authored  # noqa: PLC0415

        area = _resolve_area(kwargs.get("area_id"))
        if area is None:
            return ActionResult(success=False, message=_NO_SUCH_AREA)
        slug = kwargs.get("slug") or slugify(area.name)
        try:
            promote_to_authored(area=area, key=slug)
        except GridServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"{area.name} promoted as {slug}.")


@dataclass
class StaffPlaceClueAction(_WorldBuilderAction):
    """Place a ``RoomClue`` in a room. Kwargs: ``room_id``, ``clue_slug``, optional
    ``detect_difficulty`` (int, default 0), optional ``fixture_key`` (auto-suggested
    from ``room-<id>/<clue_slug>`` when omitted).
    """

    key: str = "staff_place_clue"
    name: str = "Place Room Clue"
    icon: str = "search"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.clues.models import Clue, RoomClue  # noqa: PLC0415

        room_profile = _resolve_room_profile(kwargs.get("room_id"))
        if room_profile is None:
            return ActionResult(success=False, message=_NO_SUCH_ROOM_MSG)
        clue_slug = (kwargs.get("clue_slug") or "").strip()
        clue = Clue.objects.filter(slug=clue_slug).first() if clue_slug else None
        if clue is None:
            return ActionResult(success=False, message="No such clue.")
        try:
            detect_difficulty = int(kwargs.get("detect_difficulty") or 0)
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Detect difficulty must be a number.")
        fixture_key = kwargs.get("fixture_key") or f"room-{room_profile.objectdb_id}/{clue_slug}"
        _room_clue, _ = RoomClue.objects.update_or_create(
            room_profile=room_profile,
            clue=clue,
            defaults={"detect_difficulty": detect_difficulty, "fixture_key": fixture_key},
        )
        return ActionResult(
            success=True, message=f"{clue.name} placed in {room_profile.objectdb.db_key}."
        )


@dataclass
class StaffRemoveClueAction(_WorldBuilderAction):
    """Remove a ``RoomClue`` placement. Kwarg: ``room_clue_id``."""

    key: str = "staff_remove_clue"
    name: str = "Remove Room Clue"
    icon: str = "trash"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        room_clue = _resolve_room_clue(kwargs.get("room_clue_id"))
        if room_clue is None:
            return ActionResult(success=False, message="No such clue placement.")
        room_clue.delete()
        return ActionResult(success=True, message="Clue placement removed.")


@dataclass
class StaffPlaceClueTriggerAction(_WorldBuilderAction):
    """Place a ``ClueTrigger`` in a room. Kwargs: ``room_id``, ``clue_slug``, optional
    ``fixture_key`` (auto-suggested from ``room-<id>/trigger-<clue_slug>`` when omitted).
    """

    key: str = "staff_place_clue_trigger"
    name: str = "Place Clue Trigger"
    icon: str = "zap"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.clues.models import Clue, ClueTrigger  # noqa: PLC0415

        room_profile = _resolve_room_profile(kwargs.get("room_id"))
        if room_profile is None:
            return ActionResult(success=False, message=_NO_SUCH_ROOM_MSG)
        clue_slug = (kwargs.get("clue_slug") or "").strip()
        clue = Clue.objects.filter(slug=clue_slug).first() if clue_slug else None
        if clue is None:
            return ActionResult(success=False, message="No such clue.")
        fixture_key = kwargs.get("fixture_key") or (
            f"room-{room_profile.objectdb_id}/trigger-{clue_slug}"
        )
        ClueTrigger.objects.update_or_create(
            room_profile=room_profile, clue=clue, defaults={"fixture_key": fixture_key}
        )
        return ActionResult(
            success=True, message=f"{clue.name} trigger placed in {room_profile.objectdb.db_key}."
        )


@dataclass
class StaffRemoveClueTriggerAction(_WorldBuilderAction):
    """Remove a ``ClueTrigger`` placement. Kwarg: ``clue_trigger_id``."""

    key: str = "staff_remove_clue_trigger"
    name: str = "Remove Clue Trigger"
    icon: str = "trash"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        trigger = _resolve_clue_trigger(kwargs.get("clue_trigger_id"))
        if trigger is None:
            return ActionResult(success=False, message="No such clue trigger.")
        trigger.delete()
        return ActionResult(success=True, message="Clue trigger removed.")


@dataclass
class StaffPlacePortalAnchorAction(_WorldBuilderAction):
    """Install a ``PortalAnchor`` from the canvas (staff variant, #2451).

    Kwargs: ``room_id``, ``kind_name``, ``name``, optional ``fixture_key``
    (auto-suggested from ``room-<id>/<kind_name-slugified>`` when omitted).
    No standing/cost gate — see ``install_portal_anchor_as_staff``.
    """

    key: str = "staff_place_portal_anchor"
    name: str = "Place Portal Anchor"
    icon: str = "door-open"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.utils.text import slugify  # noqa: PLC0415

        from world.magic.exceptions import PortalAnchorKindAlreadyInstalled  # noqa: PLC0415
        from world.magic.models import PortalAnchorKind  # noqa: PLC0415
        from world.magic.services.portal_travel import (  # noqa: PLC0415
            install_portal_anchor_as_staff,
        )

        room_profile = _resolve_room_profile(kwargs.get("room_id"))
        if room_profile is None:
            return ActionResult(success=False, message=_NO_SUCH_ROOM_MSG)
        kind_name = (kwargs.get("kind_name") or "").strip()
        kind = PortalAnchorKind.objects.filter(name__iexact=kind_name).first()
        if kind is None:
            return ActionResult(success=False, message="No such anchor kind.")
        anchor_name = (kwargs.get("name") or "").strip()
        if not anchor_name:
            return ActionResult(success=False, message="Name the anchor.")
        fixture_key = kwargs.get("fixture_key") or (
            f"room-{room_profile.objectdb_id}/{slugify(kind_name)}"
        )
        try:
            install_portal_anchor_as_staff(
                room=room_profile.objectdb,
                kind=kind,
                name=anchor_name,
                fixture_key=fixture_key,
            )
        except PortalAnchorKindAlreadyInstalled:
            return ActionResult(
                success=False, message=f"This room already has an active {kind.name} anchor."
            )
        return ActionResult(
            success=True, message=f"{anchor_name} installed in {room_profile.objectdb.db_key}."
        )


@dataclass
class StaffRemovePortalAnchorAction(_WorldBuilderAction):
    """Dissolve a ``PortalAnchor`` (soft-delete). Kwarg: ``anchor_id``."""

    key: str = "staff_remove_portal_anchor"
    name: str = "Dissolve Portal Anchor"
    icon: str = "door-closed"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.utils import timezone  # noqa: PLC0415

        anchor = _resolve_portal_anchor(kwargs.get("anchor_id"))
        if anchor is None:
            return ActionResult(success=False, message="No such active anchor.")
        anchor.dissolved_at = timezone.now()
        anchor.save(update_fields=["dissolved_at"])
        return ActionResult(success=True, message=f"{anchor.name} dissolves.")
