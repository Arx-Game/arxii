"""Value types for carried drift and the focus check (#4732)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models import Affinity


@dataclass(frozen=True)
class DriftReading:
    """How much off-aura drift a character carries against her acting aura.

    ``drift`` is the weighted sum of her balances in affinities other than the
    dominant one; ``threshold`` is the point it must pass; ``steps_past`` is how
    many ``severity_step`` bands it has passed by (0 at or below the threshold).
    ``dominant_affinity`` is None, and every number 0, when she has no aura to
    measure against.
    """

    drift: int
    threshold: int
    steps_past: int
    dominant_affinity: Affinity | None


@dataclass(frozen=True)
class FocusOutcome:
    """The result of one focus check against carried drift.

    ``steps`` is the severity the check was rolled at; ``applied_severity`` is the
    severity added to the conflict condition (0 when she kept her focus).
    """

    success_level: int
    steps: int
    applied_severity: int
