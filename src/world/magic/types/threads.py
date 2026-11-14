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
    """One resonance part of a thread's investment may be moved to (#5123).

    ``conversion_type`` is None for a retune within the source resonance's own affinity
    (rate 1), else the authored pair's Fall / Redemption type. ``projected_points`` is what
    the target's row gains from the amount being moved, at ``multiplier``.
    """

    resonance: Resonance
    conversion_type: str | None
    multiplier: Decimal
    projected_points: int


@dataclass(frozen=True)
class ThreadRetuneMove:
    """A retune that may be made: ``amount`` of ``from_resonance``'s row into ``option``.

    ``from_amount`` is the source row's total before the move.
    """

    from_resonance: Resonance
    from_amount: int
    amount: int
    option: ThreadResonanceOption


@dataclass(frozen=True)
class ThreadResonanceChangeResult:
    """The outcome of moving part of a thread's investment to another of its resonances.

    ``amount_moved`` left the ``from_resonance_id`` row; ``points_gained`` arrived on the
    ``to_resonance_id`` row (the pair rate applied across affinities). ``from_amount_after``
    and ``to_amount_after`` are the two rows' totals. The thread's level and
    ``developed_points`` are unchanged. ``message`` is the line the performer reads
    (``PerformRitualAction`` appends it, so telnet and web say the same).
    """

    thread_id: int
    from_resonance_id: int
    to_resonance_id: int
    amount_moved: int
    points_gained: int
    from_amount_after: int
    to_amount_after: int
    conversion_type: str | None
    message: str
