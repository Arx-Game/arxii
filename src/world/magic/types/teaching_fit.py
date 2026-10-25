"""Value type for the Tradition teaching fit (slice 2 of #4659)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models import Tradition, TraditionTeachingConfig


@dataclass(frozen=True)
class TeachingFit:
    """How well a Tradition's teaching fits a Gift and an aura.

    ``favored_gift_name`` / ``favored_affinity_name`` are the names of the matched
    Gift / Affinity (None when that dimension does not fit); they feed the
    player-facing "Fits: <name>" lines.
    """

    tradition: Tradition | None
    gift_fit: bool
    affinity_fit: bool
    favored_gift_name: str | None
    favored_affinity_name: str | None

    def training_bonus(self, config: TraditionTeachingConfig) -> int:
        """Training bonus earned by the dimensions that fit."""
        return (config.gift_fit_training_bonus if self.gift_fit else 0) + (
            config.affinity_fit_training_bonus if self.affinity_fit else 0
        )

    def course_ease(self, config: TraditionTeachingConfig) -> int:
        """Course ease earned by the dimensions that fit."""
        return (config.course_ease_gift_fit if self.gift_fit else 0) + (
            config.course_ease_affinity_fit if self.affinity_fit else 0
        )
