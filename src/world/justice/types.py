"""Read shapes for the justice app (#1765)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.justice.constants import HeatTier

if TYPE_CHECKING:
    from datetime import datetime

    from world.justice.models import HeatSource


@dataclass(frozen=True)
class HeatReading:
    """The pursuit picture for one persona at one spot: summed value + display tier."""

    value: int
    tier: HeatTier
    sources: list[HeatSource] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        return self.tier == HeatTier.SAFE


@dataclass(frozen=True)
class PublicMark:
    """One publicly-visible consequence standing against a persona in an area (#2378).

    Derived on read (no stored record) by :func:`world.justice.sentences.active_public_marks`
    from three sources: a still-term-limited humiliation, an active exile/banishment
    decree, or a terminal sentence pending its rescue window. ``until=None`` means a
    permanent banishment — nothing to count down to.
    """

    kind: str
    persona_name: str
    area_name: str
    until: datetime | None
