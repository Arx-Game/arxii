"""Result types for the path-crossing magic grant (#1579, ADR-0055)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models.gifts import Gift
    from world.magic.models.techniques import Technique


@dataclass(frozen=True)
class PathMagicGrantResult:
    """What a path crossing newly granted (idempotent re-grants list nothing)."""

    granted_gifts: list[Gift] = field(default_factory=list)
    granted_techniques: list[Technique] = field(default_factory=list)
