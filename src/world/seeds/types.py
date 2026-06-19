from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SeedReport:
    """Outcome of a seed run: per-cluster created-row counts."""

    clusters: dict[str, int] = field(default_factory=dict)

    @property
    def created_total(self) -> int:
        return sum(self.clusters.values())
