"""Result types for the CG gift/technique availability service (#2426)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models.techniques import Technique


@dataclass(frozen=True)
class TechniqueOptions:
    """Availability pool for one (path, gift, tradition) combination during CG.

    ``pool`` and ``tradition`` both come from the path's list for the gift
    (``PathGiftGrant.starter_techniques``, #4555): ``pool`` holds the techniques no
    Tradition grant lists, ``tradition`` the ones this tradition's grant
    (``TraditionGiftGrant.special_techniques``) lists, so the two never overlap.
    ``species`` contains techniques belonging to the selected species' granted
    gifts. Callers treat availability as the union of all three.
    """

    pool: list[Technique] = field(default_factory=list)
    tradition: list[Technique] = field(default_factory=list)
    species: list[Technique] = field(default_factory=list)
