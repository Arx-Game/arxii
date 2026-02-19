from __future__ import annotations

from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB

from evennia_extensions.models import RoomProfile
from world.areas.models import Area, AreaClosure

if TYPE_CHECKING:
    from world.areas.constants import AreaLevel
    from world.realms.models import Realm


def get_ancestry(area: Area) -> list[Area]:
    """Return the full ancestor chain from root down to this area.

    Uses the AreaClosure table for a single indexed query.
    """
    ancestor_pks = list(
        AreaClosure.objects.filter(descendant_id=area.pk)
        .order_by("-depth")
        .values_list("ancestor_id", flat=True)
    )
    if len(ancestor_pks) <= 1:
        return [area]
    ancestors_by_pk = {a.pk: a for a in Area.objects.filter(pk__in=ancestor_pks)}
    return [ancestors_by_pk[pk] for pk in ancestor_pks]


def get_ancestor_at_level(area: Area, target_level: AreaLevel) -> Area | None:
    """Walk the ancestry to find the ancestor at the given AreaLevel.

    Returns None if no ancestor exists at that level.
    """
    for ancestor in get_ancestry(area):
        if ancestor.level == target_level:
            return ancestor
    return None


def get_effective_realm(area: Area) -> Realm | None:
    """Walk up the hierarchy to find the nearest realm assignment.

    Returns None if no ancestor has a realm set.
    """
    node: Area | None = area
    while node is not None:
        if node.realm_id is not None:
            return node.realm
        node = node.parent
    return None


def get_descendant_areas(area: Area) -> list[Area]:
    """Return all areas in the subtree below this area."""
    descendant_pks = list(
        AreaClosure.objects.filter(ancestor_id=area.pk, depth__gt=0).values_list(
            "descendant_id", flat=True
        )
    )
    return list(Area.objects.filter(pk__in=descendant_pks))


def get_rooms_in_area(area: Area) -> list[RoomProfile]:
    """Return all RoomProfiles in this area and everything beneath it."""
    all_area_pks = list(
        AreaClosure.objects.filter(ancestor_id=area.pk).values_list("descendant_id", flat=True)
    )
    return list(
        RoomProfile.objects.filter(area_id__in=all_area_pks).select_related("objectdb", "area")
    )


def reparent_area(area: Area, new_parent: Area | None) -> None:
    """Move an area under a new parent.

    The AreaClosure table is refreshed automatically by Area.save(),
    so descendants' ancestry is always consistent after this call.
    """
    area.parent = new_parent
    area.save()


def get_room_profile(room_obj: ObjectDB) -> RoomProfile:
    """Get or create the RoomProfile for a room ObjectDB instance."""
    profile, _ = RoomProfile.objects.get_or_create(objectdb=room_obj)
    return profile
