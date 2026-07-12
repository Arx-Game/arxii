"""Portal travel typed payloads (#2222).

``PortalRoute`` and ``PortalDestination`` are produced by
``world.magic.services.portal_travel`` and consumed by the Task 3-5 Action /
API / telnet surfaces built on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models import PortalAnchor, PortalAnchorKind, Technique


@dataclass(frozen=True)
class PortalRoute:
    """An eligible (technique, origin anchor, destination anchor) triple.

    Returned by ``portal_route`` when the character can instantly travel from
    their current room to ``destination_anchor``'s room; consumed by
    ``perform_portal_travel``.
    """

    technique: Technique
    origin_anchor: PortalAnchor
    destination_anchor: PortalAnchor


@dataclass(frozen=True)
class PortalDestination:
    """One destination reachable via the network, for discovery UIs.

    ``room`` is the destination anchor's room ``ObjectDB`` (not its
    ``RoomProfile``) — the shape the frontend/telnet dispatch a travel
    request against.
    """

    anchor: PortalAnchor
    room: ObjectDB
    kind: PortalAnchorKind
