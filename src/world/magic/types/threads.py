from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from django.db import models

if TYPE_CHECKING:
    from decimal import Decimal

    from world.magic.models import Resonance, Thread


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
    blocked_by: Literal[
        "NONE",
        "XP_LOCK",
        "ANCHOR_CAP",
        "LEVEL_CAP",
        "INSUFFICIENT_BUCKET",
        "CROSSING_REQUIREMENT",
    ]
    blocked_requirement_messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ThreadXPLockProspect:
    """A thread that is close to an XP-locked level boundary (Spec A §3.6)."""

    thread: Thread
    boundary_level: int
    xp_cost: int
    dev_points_to_boundary: int


@dataclass(frozen=True)
class ThreadSurvivabilitySaves:
    """Per-tier survivability save baselines from thread investment (#1250)."""

    wound: int
    death: int
    knockout: int


@dataclass(frozen=True)
class ThreadResonanceOption:
    """One resonance a thread may be moved to (slice 6 of #4672).

    ``conversion_type`` is None for a retune within the thread's own affinity (rate 1),
    else the authored pair's Fall / Redemption type. ``projected_points`` is what the
    thread's ``developed_points`` become at ``multiplier``.
    """

    resonance: Resonance
    conversion_type: str | None
    multiplier: Decimal
    projected_points: int


@dataclass(frozen=True)
class ThreadResonanceChangeResult:
    """The outcome of moving a thread to another resonance.

    ``thread_id`` is the surviving thread: the moved thread itself, or, when ``merged``,
    the live thread on the same anchor that took its points (the moved one is retired).
    ``points_after`` is the survivor's ``developed_points``.
    """

    thread_id: int
    from_resonance_id: int
    to_resonance_id: int
    points_before: int
    points_moved: int
    points_after: int
    merged: bool
    conversion_type: str | None
