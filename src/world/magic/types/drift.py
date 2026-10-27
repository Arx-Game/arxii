"""Drift correction types (#4733, slice 4 of #4672)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.items.models import ItemInstance
    from world.magic.constants import ComponentMode


@dataclass(frozen=True)
class QualifyingComponent:
    """An item that counts toward a target-resonance ritual component, and the route it took."""

    item: ItemInstance
    mode: ComponentMode
