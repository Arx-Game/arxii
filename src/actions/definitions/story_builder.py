"""GM story-builder actions (#2450) — the story canvas + play-verb dispatch seam.

Category ``story_builder``; gated by MinimumGMLevelPrerequisite(STARTING)
(staff bypass built in). Ownership is checked inside execute() via the
_resolve_owned_* helpers (staff bypass there too). Thin wrappers over
world.gm.story_services + world.areas.grid_services — same substrate as the
staff canvas, scoped to the GM's own STORY-origin areas. Story rooms are
always origin=STORY, is_public=False, and never carry a fixture_key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType
from world.gm.constants import GMLevel

if TYPE_CHECKING:
    from actions.types import ActionContext
    from evennia_extensions.models import RoomProfile
    from world.areas.models import Area
    from world.gm.models import GMProfile


def _gm_profile_for(actor: ObjectDB) -> GMProfile | None:
    from world.gm.models import GMProfile  # noqa: PLC0415

    try:
        account = actor.active_account
    except AttributeError:
        return None
    if account is None:
        return None
    try:
        return account.gm_profile
    except GMProfile.DoesNotExist:
        return None


def _is_staff(actor: ObjectDB) -> bool:
    from core_management.permissions import is_staff_observer  # noqa: PLC0415

    return is_staff_observer(actor)


def _resolve_owned_story_area(actor: ObjectDB, area_id: Any) -> tuple[Area | None, str | None]:
    """Resolve area_id to a STORY area the actor owns (staff: any STORY area)."""
    from world.areas.constants import GridOrigin  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.gm.models import StoryArea  # noqa: PLC0415

    area = Area.objects.filter(pk=area_id).first() if area_id else None
    if area is None or area.origin != GridOrigin.STORY:
        return None, "No such story area."
    if _is_staff(actor):
        return area, None
    profile = _gm_profile_for(actor)
    try:
        ownership = area.story_ownership
    except StoryArea.DoesNotExist:
        ownership = None
    if profile is None or ownership is None or ownership.gm_id != profile.pk:
        return None, "That story area isn't yours."
    return area, None


def _resolve_owned_story_room(
    actor: ObjectDB, room_id: Any
) -> tuple[RoomProfile | None, str | None]:
    """Resolve room_id to a RoomProfile inside a story area the actor owns."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    if not room_id:
        return None, "No such room."
    room_profile = (
        RoomProfile.objects.filter(objectdb_id=room_id).select_related("objectdb", "area").first()
    )
    if room_profile is None or room_profile.area_id is None:
        return None, "No such room."
    _area, error = _resolve_owned_story_area(actor, room_profile.area_id)
    if error is not None:
        return None, error
    return room_profile, None


def _parse_dig_room_grid(kwargs: dict[str, Any]) -> tuple[int | None, int | None, int] | None:
    """Parse ``grid_x``/``grid_y``/``floor`` ints out of ``kwargs``.

    Deliberately duplicated from ``world_builder.py`` (a private 10-line
    helper there, #2449) rather than imported — the story-builder module
    stays self-contained the same way the staff canvas does.
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


@dataclass
class _StoryBuilderAction(Action):
    """Shared shape for the GM story-builder verbs (#2450)."""

    category: str = "story_builder"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.STARTING)]


@dataclass
class CreateStoryAreaAction(_StoryBuilderAction):
    """Create a STORY-origin area you own. Kwargs: ``name``, optional ``description``."""

    key: str = "create_story_area"
    name: str = "Create Story Area"
    icon: str = "map"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.gm.story_services import StoryServiceError, create_story_area  # noqa: PLC0415

        profile = _gm_profile_for(actor)
        if profile is None:
            return ActionResult(success=False, message="GM trust required.")
        area_name = (kwargs.get("name") or "").strip()
        if not area_name:
            return ActionResult(success=False, message="Name the area.")
        try:
            story = create_story_area(
                gm=profile, name=area_name, description=kwargs.get("description") or ""
            )
        except StoryServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"{story.area.name} created (#{story.area.pk}).")


@dataclass
class EditStoryAreaAction(_StoryBuilderAction):
    """Edit a story area you own. Kwargs: ``area_id``, optional ``name``/``description``."""

    key: str = "edit_story_area"
    name: str = "Edit Story Area"
    icon: str = "map"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        area, error = _resolve_owned_story_area(actor, kwargs.get("area_id"))
        if error is not None:
            return ActionResult(success=False, message=error)
        new_name = kwargs.get("name")
        if new_name is not None:
            new_name = new_name.strip()
            if not new_name:
                return ActionResult(success=False, message="Name the area.")
            area.name = new_name
        if kwargs.get("description") is not None:
            area.description = kwargs["description"]
        area.save()
        return ActionResult(success=True, message=f"{area.name} updated.")


@dataclass
class RemoveStoryAreaAction(_StoryBuilderAction):
    """Remove a story area you own (must be empty). Kwarg: ``area_id``."""

    key: str = "remove_story_area"
    name: str = "Remove Story Area"
    icon: str = "trash"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.gm.story_services import StoryServiceError, remove_story_area  # noqa: PLC0415

        area, error = _resolve_owned_story_area(actor, kwargs.get("area_id"))
        if error is not None:
            return ActionResult(success=False, message=error)
        try:
            remove_story_area(story=area.story_ownership)
        except StoryServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Story area removed.")


@dataclass
class StoryDigRoomAction(_StoryBuilderAction):
    """Dig a room into a story area you own.

    Kwargs: ``area_id``, ``name``, optional ``description``/``grid_x``/
    ``grid_y``/``floor``. Story rooms are always ``origin=STORY``,
    ``is_public=False``, and never carry a ``fixture_key``.
    """

    key: str = "story_dig_room"
    name: str = "Dig Story Room"
    icon: str = "hammer"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.areas.constants import GridOrigin  # noqa: PLC0415
        from world.areas.grid_services import cell_occupied, create_room  # noqa: PLC0415
        from world.gm.story_services import StoryServiceError, story_room_cap_check  # noqa: PLC0415

        area, error = _resolve_owned_story_area(actor, kwargs.get("area_id"))
        if error is not None:
            return ActionResult(success=False, message=error)
        room_name = (kwargs.get("name") or "").strip()
        if not room_name:
            return ActionResult(success=False, message="Name the room.")
        if not _is_staff(actor):
            # Staff is uncapped (mirrors staff_dig_room); a GM is always cap-checked.
            profile = _gm_profile_for(actor)
            if profile is None:
                return ActionResult(success=False, message="GM trust required.")
            try:
                story_room_cap_check(gm=profile, area=area)
            except StoryServiceError as exc:
                return ActionResult(success=False, message=exc.user_message)
        parsed_grid = _parse_dig_room_grid(kwargs)
        if parsed_grid is None:
            return ActionResult(success=False, message="Grid position and floor must be numbers.")
        grid_x, grid_y, floor = parsed_grid
        unplaced_note = ""
        if grid_x is not None and grid_y is not None and cell_occupied(area, grid_x, grid_y, floor):
            # Cosmetic coordinates never block creation (mirrors staff_dig_room's
            # precedent) — place_room_on_grid is the verb that still raises.
            grid_x = None
            grid_y = None
            unplaced_note = (
                " That cell was occupied — room created unplaced; drag it into position."
            )
        profile_row = create_room(
            area=area,
            name=room_name,
            description=kwargs.get("description") or "",
            size=None,
            grid_x=grid_x,
            grid_y=grid_y,
            floor=floor,
            origin=GridOrigin.STORY,
            fixture_key=None,
        )
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415

        RoomProfile.objects.filter(pk=profile_row.pk).update(is_public=False)
        profile_row.is_public = False
        return ActionResult(
            success=True,
            message=f"{profile_row.objectdb.db_key} dug (#{profile_row.pk}).{unplaced_note}",
        )


@dataclass
class StoryEditRoomAction(_StoryBuilderAction):
    """Edit a story room's display data. Kwargs: ``room_id``, optional ``name``/``description``."""

    key: str = "story_edit_room"
    name: str = "Edit Story Room"
    icon: str = "pencil"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.locations.services import RoomEditError, set_room_display_data  # noqa: PLC0415

        room_profile, error = _resolve_owned_story_room(actor, kwargs.get("room_id"))
        if error is not None:
            return ActionResult(success=False, message=error)
        display_name = kwargs.get("name")
        description = kwargs.get("description")
        if display_name is not None or description is not None:
            try:
                set_room_display_data(
                    room=room_profile.objectdb,
                    persona=None,
                    name=display_name,
                    description=description,
                    bypass_ownership=True,
                )
            except RoomEditError as exc:
                return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"{room_profile.objectdb.db_key} updated.")
