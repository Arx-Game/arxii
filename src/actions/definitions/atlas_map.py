"""Staff world-map actions (#4242): the Atlas's region maps, footprints and paint.

Three REGISTRY actions, ``category="almanach"`` like the ladder verbs they sit
beside, ``target_type=SELF``, gated by ``StaffOnlyPrerequisite`` — the shared
``action.run()`` seam the Atlas's region-map view dispatches through. Each is a
thin wrapper over ``world.areas.worldmap.services``; every refusal is a plain
``ActionResult(success=False, message=...)`` from the service's
``user_message``, never ``str(exc)``. The one write that is not here is the
file upload, a multipart endpoint on the region-maps API (a file does not
travel in action kwargs). Create Domain from the map is ``almanach_plant_rung``
followed by ``atlas_carve_footprint``; nothing here mints a rung.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import Prerequisite, StaffOnlyPrerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

_NO_SUCH_REGION = "No such region map."
_NO_SUCH_AREA = "No such area."


def _pip_list(value: Any) -> list[tuple[int, int]] | None:
    """Kwarg ``[[x, y], ...]`` as pairs, or None when it is not that shape."""
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        return None
    out: list[tuple[int, int]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:  # noqa: PLR2004
            return None
        try:
            out.append((int(item[0]), int(item[1])))
        except (TypeError, ValueError):
            return None
    return out


def _carve_target(kwargs: dict[str, Any]) -> Any:
    """The area a carve names: by ``area_id``, or by ``title_id`` through the rung walk."""
    from world.areas.models import Area  # noqa: PLC0415
    from world.societies.houses.almanach import rung_area_for_title  # noqa: PLC0415
    from world.societies.houses.models import Title  # noqa: PLC0415
    from world.societies.houses.services import HousesServiceError  # noqa: PLC0415

    if kwargs.get("title_id"):
        title = Title.objects.filter(pk=kwargs["title_id"]).first()
        if title is None:
            return None
        try:
            return rung_area_for_title(title)
        except HousesServiceError:
            return None
    return Area.objects.filter(pk=kwargs.get("area_id")).first()


@dataclass
class _AtlasMapAction(Action):
    """Shared shape for the staff world-map verbs (#4242)."""

    category: str = "almanach"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [StaffOnlyPrerequisite()]


@dataclass
class AtlasCreateRegionMapAction(_AtlasMapAction):
    """Place a region on the world grid, ready for its first upload.

    Kwargs: ``name``, ``anchor_x``, ``anchor_y`` (world cells), ``width_cells``,
    optional ``area_id`` (the continent-level Area it is the geography of) or
    ``new_continent`` (link the CONTINENT rung by the region's name, creating it
    when there is none).
    """

    key: str = "atlas_create_region_map"
    name: str = "Create Region Map"
    icon: str = "map"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.areas.models import Area  # noqa: PLC0415
        from world.areas.worldmap.services import (  # noqa: PLC0415
            WorldMapServiceError,
            create_region_map,
        )

        try:
            anchor_x = int(kwargs.get("anchor_x", 0))
            anchor_y = int(kwargs.get("anchor_y", 0))
            width_cells = int(kwargs.get("width_cells", 0))
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Anchor and width are whole numbers.")
        area = None
        if kwargs.get("area_id"):
            area = Area.objects.filter(pk=kwargs["area_id"]).first()
            if area is None:
                return ActionResult(success=False, message=_NO_SUCH_AREA)
        try:
            region = create_region_map(
                name=str(kwargs.get("name") or ""),
                anchor_x=anchor_x,
                anchor_y=anchor_y,
                width_cells=width_cells,
                area=area,
                new_continent=bool(kwargs.get("new_continent")),
                actor=actor.db_account,
            )
        except WorldMapServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{region.name} placed at cell ({region.anchor_x}, {region.anchor_y}).",
            data={"region_id": region.pk},
        )


@dataclass
class AtlasCarveFootprintAction(_AtlasMapAction):
    """Grow or shrink a domain's footprint on the map.

    Kwargs: ``area_id`` or ``title_id`` (the rung's own area, the walk the Almanach
    does), ``add`` and ``remove`` as lists of ``[x, y]`` world pips.
    """

    key: str = "atlas_carve_footprint"
    name: str = "Carve Footprint"
    icon: str = "map"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.areas.worldmap.services import (  # noqa: PLC0415
            WorldMapServiceError,
            set_footprint,
        )

        area = _carve_target(kwargs)
        if area is None:
            return ActionResult(success=False, message=_NO_SUCH_AREA)
        add, remove = _pip_list(kwargs.get("add")), _pip_list(kwargs.get("remove"))
        if add is None or remove is None:
            return ActionResult(success=False, message="Pips are lists of [x, y] pairs.")
        try:
            change = set_footprint(area=area, add=add, remove=remove)
        except WorldMapServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        name = area.name or "The domain"
        message = f"{name}: {change.added} pips added, {change.removed} removed."
        if change.skipped:
            holders = ", ".join(change.skipped_holders)
            message += f" {change.skipped} skipped ({holders})."
        return ActionResult(
            success=True,
            message=message,
            data={
                "area_id": area.pk,
                "added": change.added,
                "removed": change.removed,
                "skipped": change.skipped,
            },
        )


@dataclass
class AtlasPaintTerrainAction(_AtlasMapAction):
    """Paint pips with a terrain as a staff edit that survives re-uploads.

    Kwargs: ``region_id``, ``pips`` as a list of ``[x, y]`` world pips, ``terrain``.
    """

    key: str = "atlas_paint_terrain"
    name: str = "Paint Terrain"
    icon: str = "map"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.areas.worldmap.models import RegionMap  # noqa: PLC0415
        from world.areas.worldmap.services import (  # noqa: PLC0415
            WorldMapServiceError,
            paint_terrain,
        )

        region = RegionMap.objects.filter(pk=kwargs.get("region_id")).first()
        if region is None:
            return ActionResult(success=False, message=_NO_SUCH_REGION)
        pips = _pip_list(kwargs.get("pips"))
        if pips is None:
            return ActionResult(success=False, message="Pips are lists of [x, y] pairs.")
        try:
            count = paint_terrain(
                region=region, pips=pips, terrain=str(kwargs.get("terrain") or "")
            )
        except WorldMapServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{count} pips painted {kwargs.get('terrain')}.",
            data={"region_id": region.pk, "painted": count},
        )
