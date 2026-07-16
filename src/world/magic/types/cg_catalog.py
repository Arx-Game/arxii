"""Result types for the CG gift/technique availability service (#2426)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models.techniques import Technique


@dataclass(frozen=True)
class TechniqueOptions:
    """Availability pool for one (path, gift, tradition) combination during CG.

    ``pool`` is the path's curated starter set (``PathGiftGrant.starter_techniques``);
    ``signature`` is the tradition's curated signature set
    (``TraditionGiftGrant.signature_techniques``). The two lists are not deduplicated
    here — callers treat availability as the union ``pool`` U ``signature``.
    """

    pool: list[Technique] = field(default_factory=list)
    signature: list[Technique] = field(default_factory=list)
