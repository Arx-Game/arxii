from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q
from evennia.objects.models import ObjectDB

from evennia_extensions.models import RoomProfile
from world.areas.models import Area

if TYPE_CHECKING:
    from world.areas.constants import AreaLevel
    from world.realms.models import Realm


def get_ancestry(area: Area) -> list[Area]:
    """Return the full ancestor chain from root down to this area.

    Uses a single filter query then re-sorts by path order.
    """
    if not area.mat_path:
        return [area]
    ancestor_pks = [int(pk) for pk in area.mat_path.split("/")]
    ancestors_by_pk = {a.pk: a for a in Area.objects.filter(pk__in=ancestor_pks)}
    ancestors = [ancestors_by_pk[pk] for pk in ancestor_pks]
    ancestors.append(area)
    return ancestors


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


def _subtree_prefix(area: Area) -> str:
    """Build the materialized-path prefix that all descendants share."""
    if area.mat_path:
        return f"{area.mat_path}/{area.pk}"
    return str(area.pk)


def get_descendant_areas(area: Area) -> list[Area]:
    """Return all areas in the subtree below this area."""
    prefix = _subtree_prefix(area)
    return list(Area.objects.filter(Q(mat_path=prefix) | Q(mat_path__startswith=f"{prefix}/")))


def get_rooms_in_area(area: Area) -> list[RoomProfile]:
    """Return all RoomProfiles in this area and everything beneath it."""
    prefix = _subtree_prefix(area)
    return list(
        RoomProfile.objects.filter(
            Q(area=area) | Q(area__mat_path=prefix) | Q(area__mat_path__startswith=f"{prefix}/")
        ).select_related("objectdb", "area")
    )


def reparent_area(area: Area, new_parent: Area | None) -> None:
    """Move an area under a new parent, updating all descendant paths."""
    with transaction.atomic():
        old_prefix = _subtree_prefix(area)

        area.parent = new_parent
        area.full_clean()
        area.mat_path = area.build_mat_path()
        area.save()

        new_prefix = _subtree_prefix(area)

        descendants = Area.objects.filter(
            Q(mat_path=old_prefix) | Q(mat_path__startswith=f"{old_prefix}/")
        )
        for descendant in descendants:
            descendant.mat_path = new_prefix + descendant.mat_path[len(old_prefix) :]
            descendant.save()


def get_room_profile(room_obj: ObjectDB) -> RoomProfile:
    """Get or create the RoomProfile for a room ObjectDB instance."""
    profile, _ = RoomProfile.objects.get_or_create(objectdb=room_obj)
    return profile
