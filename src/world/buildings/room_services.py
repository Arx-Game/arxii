"""Room Builder services (#670): dig / resize / remove / link rooms, budgets.

The owner-facing mutation layer for laying out a building's interior. All
functions re-check permissions as a hard boundary (action prerequisites are
the primary UX gate, per the slice-1 ``set_room_display_data`` pattern) and
raise ``RoomBuildError`` subclasses carrying a player-facing ``user_message``.

Design (ratified on #670):
- Rooms within the building's ``space_budget`` are instant and free —
  construction/extension projects already paid for the space.
- ``dig_room`` is the stub-creation verb (direction + name required, all else
  defaulted); refinement happens through single-field edits afterwards.
- Grid coordinates are cosmetic only and never block creation: a dig whose
  target cell is occupied simply lands unplaced.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import models, transaction
from django.db.models import Sum

from evennia_extensions.models import RoomProfile, RoomSizeTier
from evennia_extensions.seeds import DEFAULT_ROOM_SIZE_NAME
from world.buildings.models import Building
from world.buildings.room_constants import DIRECTIONS, UNFINISHED_ROOM_DESC

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from world.scenes.models import Persona

logger = logging.getLogger(__name__)


class RoomBuildError(Exception):
    """A room-builder operation was refused; carries ``user_message``.

    Never surface ``str(exc)`` to API responses — use ``exc.user_message``.
    """

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def building_for_room(room: DefaultObject) -> Building | None:
    """The Building whose Area this room belongs to, or None outside buildings."""
    try:
        profile = room.room_profile
    except RoomProfile.DoesNotExist:
        return None
    if profile.area_id is None:
        return None
    return Building.objects.filter(area_id=profile.area_id).first()


def space_used(building: Building) -> int:
    """Total room-size units currently spent in this building.

    Unsized rooms (``size`` NULL) count as 0 — they predate the budget system.
    """
    total = RoomProfile.objects.filter(area=building.area).aggregate(total=Sum("size__units"))[
        "total"
    ]
    return total or 0


def space_remaining(building: Building) -> int:
    return max(0, building.space_budget - space_used(building))


def _require_building_owner(persona: Persona, room: DefaultObject) -> Building:
    """Resolve the room's Building and require ownership standing on the room."""
    from world.locations.services import is_owner  # noqa: PLC0415

    building = building_for_room(room)
    if building is None:
        msg = "This room isn't part of a building."
        raise RoomBuildError(msg)
    if not is_owner(persona, room):
        msg = "Only the building's owner can restructure it."
        raise RoomBuildError(msg)
    return building


def _cell_occupied(building: Building, x: int, y: int, floor: int) -> bool:
    return RoomProfile.objects.filter(area=building.area, grid_x=x, grid_y=y, floor=floor).exists()


def _set_room_description(room: DefaultObject, description: str) -> None:
    from evennia_extensions.models import ObjectDisplayData  # noqa: PLC0415

    display, _ = ObjectDisplayData.objects.get_or_create(object=room)
    display.permanent_description = description
    display.save()


def _room_description(room: DefaultObject) -> str:
    from evennia_extensions.models import ObjectDisplayData  # noqa: PLC0415

    display = ObjectDisplayData.objects.filter(object=room).first()
    return display.permanent_description if display else ""


def _create_exit(
    *, name: str, aliases: tuple[str, ...], source: DefaultObject, destination: DefaultObject
) -> DefaultObject:
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    exit_obj = ObjectDB.objects.create(
        db_key=name,
        db_typeclass_path="typeclasses.exits.Exit",
        db_location=source,
        db_destination=destination,
    )
    for alias in aliases:
        exit_obj.aliases.add(alias)
    return exit_obj


def _resolve_like_profile(like: DefaultObject | None, building: Building) -> RoomProfile | None:
    """Validate + resolve the ``like=`` exemplar room within the same building."""
    if like is None:
        return None
    try:
        like_profile = like.room_profile
    except RoomProfile.DoesNotExist as exc:
        msg = "That room can't be used as a model."
        raise RoomBuildError(msg) from exc
    if like_profile.area_id != building.area_id:
        msg = "The model room must be in the same building."
        raise RoomBuildError(msg)
    return like_profile


def _charge_budget(building: Building, name: str, size: RoomSizeTier | None) -> None:
    """Refuse when the room's units exceed the remaining space budget."""
    cost = size.units if size else 0
    remaining = space_remaining(building)
    if cost > remaining:
        msg = (
            f"Not enough space: {name} needs {cost} units but only {remaining} of "
            f"{building.space_budget} remain. Extend the building or resize rooms."
        )
        raise RoomBuildError(msg)


def dig_room(  # noqa: PLR0913 — dig's optional knobs are the ratified UX surface
    *,
    persona: Persona,
    from_room: DefaultObject,
    direction: str,
    name: str,
    description: str = "",
    like: DefaultObject | None = None,
    size: RoomSizeTier | None = None,
) -> RoomProfile:
    """Create a stub room off ``from_room``, connected by a direction exit pair.

    Only ``direction`` + ``name`` are required (the ratified dig rhythm):
    size defaults to the exemplar's (``like``), else the seeded default tier;
    description defaults to the exemplar's, else the PLACEHOLDER stub text.
    Instant and free within the space budget. Freeform-named connections
    between existing rooms are ``link_rooms``'s job, not dig's.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    direction = direction.strip().lower()
    spec = DIRECTIONS.get(direction)
    if spec is None:
        options = ", ".join(DIRECTIONS)
        msg = f"'{direction}' isn't a direction. Dig one of: {options}."
        raise RoomBuildError(msg)
    if not name.strip():
        msg = "The new room needs a name."
        raise RoomBuildError(msg)

    building = _require_building_owner(persona, from_room)
    from_profile = from_room.room_profile
    like_profile = _resolve_like_profile(like, building)

    new_size = size or (like_profile.size if like_profile else None)
    if new_size is None:
        new_size = RoomSizeTier.objects.filter(name=DEFAULT_ROOM_SIZE_NAME).first()
    _charge_budget(building, name, new_size)

    if not description:
        description = _room_description(like) if like is not None else ""
    description = description or UNFINISHED_ROOM_DESC

    # Cosmetic coordinates — never block creation on them.
    grid_x = grid_y = None
    floor = from_profile.floor + spec.dfloor
    if from_profile.grid_x is not None and from_profile.grid_y is not None:
        tx, ty = from_profile.grid_x + spec.dx, from_profile.grid_y + spec.dy
        if not _cell_occupied(building, tx, ty, floor):
            grid_x, grid_y = tx, ty

    with transaction.atomic():
        room = ObjectDB.objects.create(
            db_key=name.strip(),
            db_typeclass_path="typeclasses.rooms.Room",
        )
        profile, _ = RoomProfile.objects.update_or_create(
            objectdb=room,
            defaults={
                "area": building.area,
                "is_outdoor": False,
                "size": new_size,
                "grid_x": grid_x,
                "grid_y": grid_y,
                "floor": floor,
            },
        )
        _set_room_description(room, description)
        reverse = DIRECTIONS[spec.opposite]
        _create_exit(name=direction, aliases=spec.aliases, source=from_room, destination=room)
        _create_exit(
            name=spec.opposite, aliases=reverse.aliases, source=room, destination=from_room
        )
    logger.info(
        "dig_room: %s dug %s %s of room %s in building %s (%d/%d units used).",
        persona.pk,
        room.pk,
        direction,
        from_room.pk,
        building.pk,
        space_used(building),
        building.space_budget,
    )
    return profile


def resize_room(*, persona: Persona, room: DefaultObject, size: RoomSizeTier) -> RoomProfile:
    """Change a room's size tier, instant within the remaining budget."""
    building = _require_building_owner(persona, room)
    profile = room.room_profile
    current = profile.size.units if profile.size else 0
    delta = size.units - current
    if delta > space_remaining(building):
        _charge_budget(building, room.db_key, size)  # raises with used/total detail
    profile.size = size
    profile.save(update_fields=["size"])
    return profile


def _building_exits(building: Building) -> list[DefaultObject]:
    """All Exit objects whose source room is in this building."""
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    room_ids = RoomProfile.objects.filter(area=building.area).values_list("objectdb_id", flat=True)
    return list(
        ObjectDB.objects.filter(
            db_typeclass_path="typeclasses.exits.Exit",
            db_location_id__in=list(room_ids),
            db_destination_id__in=list(room_ids),
        )
    )


def _stranded_rooms(
    building: Building,
    *,
    drop_room_id: int | None = None,
    drop_exit_ids: frozenset[int] = frozenset(),
) -> list[str]:
    """Names of rooms unreachable from the entry room after a hypothetical removal.

    BFS over the building's exit graph, skipping the dropped room / exits.
    Buildings top out at a few hundred rooms, so this is cheap.
    """
    entry = building.entry_room
    if entry is None or entry.objectdb_id == drop_room_id:
        return []
    room_ids = set(
        RoomProfile.objects.filter(area=building.area).values_list("objectdb_id", flat=True)
    )
    room_ids.discard(drop_room_id)
    adjacency: dict[int, set[int]] = {rid: set() for rid in room_ids}
    for exit_obj in _building_exits(building):
        if exit_obj.pk in drop_exit_ids:
            continue
        src, dst = exit_obj.db_location_id, exit_obj.db_destination_id
        if src in room_ids and dst in room_ids:
            adjacency[src].add(dst)
            adjacency[dst].add(src)
    seen = {entry.objectdb_id}
    frontier = [entry.objectdb_id]
    while frontier:
        current = frontier.pop()
        for neighbor in adjacency.get(current, ()):
            if neighbor not in seen:
                seen.add(neighbor)
                frontier.append(neighbor)
    orphaned = room_ids - seen
    if not orphaned:
        return []
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    return list(ObjectDB.objects.filter(pk__in=orphaned).values_list("db_key", flat=True))


def link_rooms(
    *,
    persona: Persona,
    room_a: DefaultObject,
    room_b: DefaultObject,
    name_ab: str,
    name_ba: str,
) -> None:
    """Create a named exit pair between two existing rooms in the same building.

    This is where freeform exit names live ("through the oak door");
    directional digs derive theirs from the direction.
    """
    building = _require_building_owner(persona, room_a)
    for other in (room_b,):
        try:
            other_profile = other.room_profile
        except RoomProfile.DoesNotExist as exc:
            msg = "Both rooms must be in this building."
            raise RoomBuildError(msg) from exc
        if other_profile.area_id != building.area_id:
            msg = "Both rooms must be in this building."
            raise RoomBuildError(msg)
    if not name_ab.strip() or not name_ba.strip():
        msg = "Both exit names are needed (one for each direction)."
        raise RoomBuildError(msg)
    spec_ab = DIRECTIONS.get(name_ab.strip().lower())
    spec_ba = DIRECTIONS.get(name_ba.strip().lower())
    with transaction.atomic():
        _create_exit(
            name=name_ab.strip(),
            aliases=spec_ab.aliases if spec_ab else (),
            source=room_a,
            destination=room_b,
        )
        _create_exit(
            name=name_ba.strip(),
            aliases=spec_ba.aliases if spec_ba else (),
            source=room_b,
            destination=room_a,
        )


def _exit_pair(exit_obj: DefaultObject) -> list[DefaultObject]:
    """The exit and its reverse-direction sibling (if one exists)."""
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    pair = [exit_obj]
    reverse = ObjectDB.objects.filter(
        db_typeclass_path="typeclasses.exits.Exit",
        db_location=exit_obj.db_destination,
        db_destination=exit_obj.db_location,
    ).first()
    if reverse is not None:
        pair.append(reverse)
    return pair


def unlink_rooms(*, persona: Persona, exit_obj: DefaultObject) -> None:
    """Remove an exit (and its reverse sibling), refusing to strand rooms."""
    source = exit_obj.db_location
    building = _require_building_owner(persona, source)
    pair = _exit_pair(exit_obj)
    stranded = _stranded_rooms(building, drop_exit_ids=frozenset(e.pk for e in pair))
    if stranded:
        names = ", ".join(sorted(stranded))
        msg = f"Removing that exit would cut off: {names}. Link them another way first."
        raise RoomBuildError(msg)
    for e in pair:
        e.delete()


def rename_exit(*, persona: Persona, exit_obj: DefaultObject, name: str) -> None:
    """Rename one direction of an exit (the reverse keeps its own name)."""
    _require_building_owner(persona, exit_obj.db_location)
    if not name.strip():
        msg = "The exit needs a name."
        raise RoomBuildError(msg)
    exit_obj.db_key = name.strip()
    exit_obj.save(update_fields=["db_key"])


def _room_removal_guards(building: Building, room: DefaultObject) -> None:
    """Raise RoomBuildError when the room can't be removed."""
    profile = room.room_profile
    if building.entry_room_id == profile.pk:
        msg = "The entry room can't be removed — it's the building's way in."
        raise RoomBuildError(msg)
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    if RoomFeatureInstance.objects.filter(room_profile=profile).active().exists():
        msg = "This room has an installed feature; remove that first."
        raise RoomBuildError(msg)
    from world.buildings.models import InteriorDesignDetails  # noqa: PLC0415
    from world.projects.constants import ProjectStatus  # noqa: PLC0415

    active_design = InteriorDesignDetails.objects.filter(
        room=profile,
        project__status__in=(ProjectStatus.PLANNING, ProjectStatus.ACTIVE),
    ).exists()
    if active_design:
        msg = "A decoration project is underway in this room; it must finish or be cancelled."
        raise RoomBuildError(msg)
    stranded = _stranded_rooms(building, drop_room_id=room.pk)
    if stranded:
        names = ", ".join(sorted(stranded))
        msg = f"Removing this room would cut off: {names}. Re-link them first."
        raise RoomBuildError(msg)


def remove_room(*, persona: Persona, room: DefaultObject) -> None:
    """Remove a room: evict tenants + contents to the entry room, delete exits.

    Budget reclaims implicitly (the room's units stop counting). Guards:
    never the entry room, no installed feature, and the exit graph must
    stay connected without it. (An active decoration project targeting the
    room also blocks — checked once INTERIOR_DESIGN lands.)
    """
    from django.utils import timezone  # noqa: PLC0415
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from world.locations.models import LocationTenancy  # noqa: PLC0415

    building = _require_building_owner(persona, room)
    _room_removal_guards(building, room)
    profile = room.room_profile
    entry_obj = building.entry_room.objectdb if building.entry_room else None

    now = timezone.now()
    with transaction.atomic():
        LocationTenancy.objects.filter(room_profile=profile).filter(
            models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now)
        ).update(ends_at=now)
        if entry_obj is not None:
            for obj in list(room.contents):
                obj.move_to(entry_obj, quiet=True)
        ObjectDB.objects.filter(
            db_typeclass_path="typeclasses.exits.Exit",
            db_location=room,
        ).delete()
        ObjectDB.objects.filter(
            db_typeclass_path="typeclasses.exits.Exit",
            db_destination=room,
        ).delete()
        room.delete()


# ---------------------------------------------------------------------------
# BUILDING_EXTENSION — grow the space budget via a funded project (#670)
# ---------------------------------------------------------------------------


def start_building_extension(*, persona: Persona, building: Building, added_budget: int):
    """Open a BUILDING_EXTENSION project adding ``added_budget`` units on completion.

    Owner-gated. Threshold scales with the budget added
    (``EXTENSION_THRESHOLD_PER_UNIT``, PLACEHOLDER pending the economy pass);
    funding flows through the standard contribution pipe.
    """
    from datetime import timedelta  # noqa: PLC0415

    from django.utils import timezone  # noqa: PLC0415

    from world.buildings.models import BuildingExtensionDetails  # noqa: PLC0415
    from world.buildings.room_constants import EXTENSION_THRESHOLD_PER_UNIT  # noqa: PLC0415
    from world.locations.services import is_owner  # noqa: PLC0415
    from world.projects.constants import CompletionMode, ProjectKind  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415

    entry = building.entry_room
    if entry is None or not is_owner(persona, entry.objectdb):
        msg = "Only the building's owner can extend it."
        raise RoomBuildError(msg)
    if added_budget < 1:
        msg = "The extension must add at least one unit of space."
        raise RoomBuildError(msg)

    now = timezone.now()
    with transaction.atomic():
        project = Project.objects.create(
            kind=ProjectKind.BUILDING_EXTENSION,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=30),
            threshold_target=added_budget * EXTENSION_THRESHOLD_PER_UNIT,
            description=f"Extend {building} by {added_budget} units",
        )
        BuildingExtensionDetails.objects.create(
            project=project,
            building=building,
            added_budget=added_budget,
        )
    return project


def complete_building_extension(project, outcome_tier: object | None = None) -> None:  # noqa: ARG001
    """Kind handler: apply the extension's budget to the building, exactly once.

    Registered with ``register_kind_handler`` at app-ready time; signature
    matches the framework's ``KindHandler`` (project, outcome_tier).
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.buildings.models import BuildingExtensionDetails  # noqa: PLC0415

    with transaction.atomic():
        # The claim filter hits the DB, so a second call sees the non-null
        # applied_at and no-ops even though the cached instance is stale.
        claimed = BuildingExtensionDetails.objects.filter(
            project=project, applied_at__isnull=True
        ).update(applied_at=timezone.now())
        if not claimed:
            return
        details = BuildingExtensionDetails.objects.get(project=project)
        # Instance mutation, not queryset .update(): SharedMemoryModel keeps
        # one live instance per row, and a queryset update would leave every
        # holder of it (including this test run) reading the old budget.
        building = details.building
        building.space_budget += details.added_budget
        building.save(update_fields=["space_budget"])
    logger.info(
        "building extension %s applied: +%d units to building %s.",
        project.pk,
        details.added_budget,
        details.building_id,
    )


# ---------------------------------------------------------------------------
# INTERIOR_DESIGN — commission a polish template against a building/room (#670)
# ---------------------------------------------------------------------------


def _check_template_prerequisites(building: Building, template) -> None:
    """Refuse commissioning when the building misses a tier prerequisite."""
    from world.buildings.models import BuildingPolish  # noqa: PLC0415

    for prereq in template.tier_prerequisites.select_related("category"):
        row = BuildingPolish.objects.filter(building=building, category=prereq.category).first()
        current = row.value if row else 0
        if current < prereq.min_value:
            msg = (
                f"'{template.name}' needs {prereq.category.name} at "
                f"{prereq.tier_name} ({prereq.min_value}); this building is at {current}."
            )
            raise RoomBuildError(msg)


def commission_decoration(
    *,
    persona: Persona,
    building: Building,
    template,
    room: DefaultObject | None = None,
):
    """Open an INTERIOR_DESIGN project applying ``template``'s polish on completion.

    Owner-gated; checks the template's tier prerequisites against the
    building's current polish. ``room=None`` targets the whole building.
    Threshold = the template's admin-authored ``base_cost``.
    """
    from datetime import timedelta  # noqa: PLC0415

    from django.utils import timezone  # noqa: PLC0415

    from world.buildings.models import InteriorDesignDetails  # noqa: PLC0415
    from world.locations.services import is_owner  # noqa: PLC0415
    from world.projects.constants import CompletionMode, ProjectKind  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415

    entry = building.entry_room
    if entry is None or not is_owner(persona, entry.objectdb):
        msg = "Only the building's owner can commission decoration."
        raise RoomBuildError(msg)
    room_profile = None
    if room is not None:
        try:
            room_profile = room.room_profile
        except RoomProfile.DoesNotExist as exc:
            msg = "That room isn't part of this building."
            raise RoomBuildError(msg) from exc
        if room_profile.area_id != building.area_id:
            msg = "That room isn't part of this building."
            raise RoomBuildError(msg)
    _check_template_prerequisites(building, template)

    now = timezone.now()
    with transaction.atomic():
        project = Project.objects.create(
            kind=ProjectKind.INTERIOR_DESIGN,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=30),
            threshold_target=max(1, template.base_cost),
            description=f"Commission '{template.name}'",
        )
        InteriorDesignDetails.objects.create(
            project=project,
            template=template,
            building=building,
            room=room_profile,
        )
    return project


def complete_interior_design(project, outcome_tier: object | None = None) -> None:  # noqa: ARG001
    """Kind handler: apply the commissioned template's polish, exactly once.

    Building target → ``apply_project_completion`` (snapshot + polish rows).
    Room target → each ``ProjectTemplatePolishIncrement`` through
    ``apply_room_polish_delta`` (which also recomputes prestige).
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.buildings.models import InteriorDesignDetails  # noqa: PLC0415
    from world.buildings.polish_services import (  # noqa: PLC0415
        apply_project_completion,
        apply_room_polish_delta,
    )

    with transaction.atomic():
        claimed = InteriorDesignDetails.objects.filter(
            project=project, applied_at__isnull=True
        ).update(applied_at=timezone.now())
        if not claimed:
            return
        details = InteriorDesignDetails.objects.select_related("template", "building", "room").get(
            project=project
        )
        if details.room is None:
            apply_project_completion(details.building, details.template, source_project=project)
        else:
            for increment in details.template.polish_increment_rows.select_related("category"):
                apply_room_polish_delta(details.room, increment.category, increment.value)
    logger.info("interior design %s applied (template %s).", project.pk, details.template_id)
