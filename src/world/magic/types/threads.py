from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from django.db import models

if TYPE_CHECKING:
    from world.magic.models import Thread


class ThreadAxis(models.TextChoices):
    """The axes along which magical threads (relationships) are measured."""

    ROMANTIC = "romantic", "Romantic"
    TRUST = "trust", "Trust"
    RIVALRY = "rivalry", "Rivalry"
    PROTECTIVE = "protective", "Protective"
    ENMITY = "enmity", "Enmity"


@dataclass(frozen=True)
class ThreadImbueResult:
    """Result of spend_resonance_for_imbuing (Spec A §3.2)."""

    resonance_spent: int
    developed_points_added: int
    levels_gained: int
    new_level: int
    new_developed_points: int
    blocked_by: Literal["NONE", "XP_LOCK", "ANCHOR_CAP", "PATH_CAP", "INSUFFICIENT_BUCKET"]


@dataclass(frozen=True)
class ThreadXPLockProspect:
    """A thread that is close to an XP-locked level boundary (Spec A §3.6)."""

    thread: Thread
    boundary_level: int
    xp_cost: int
    dev_points_to_boundary: int
