"""Typed menu target identities and server-only resolved targets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.items.models import ItemInstance
    from world.scenes.place_models import Place


class MenuTargetKind(StrEnum):
    """The database ID domain named by a menu request."""

    ITEMS = "items"
    OBJECTS = "objects"
    EXITS = "exits"
    PLACES = "places"


@dataclass(frozen=True)
class MenuTargetRequest:
    """Name a target with optional context assertions, never authority."""

    kind: MenuTargetKind
    target_id: int
    owner_persona_id: int | None = None
    container_item_id: int | None = None


@dataclass(frozen=True)
class ResolvedMenuTarget:
    """Carry a target the viewer may identify inside the server only."""

    request: MenuTargetRequest
    label: str
    item: ItemInstance | None = None
    game_object: ObjectDB | None = None
    place: Place | None = None
