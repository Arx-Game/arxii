from __future__ import annotations

from typing import TYPE_CHECKING

from world.areas.models import Area

if TYPE_CHECKING:
    from world.areas.constants import AreaLevel
    from world.realms.models import Realm


def get_ancestry(area: Area) -> list[Area]:
    """Return the full ancestor chain from root down to this area.

    Uses SharedMemoryModel cache -- no DB queries after first access.
    """
    if not area.path:
        return [area]
    ancestor_pks = [int(pk) for pk in area.path.split("/")]
    ancestors = [Area.objects.get(pk=pk) for pk in ancestor_pks]
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
