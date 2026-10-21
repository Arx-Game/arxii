"""Value types for NPC services (#4091)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllegianceEnding:
    """How an allegiance hold ended: which condition, and the authored result picked."""

    condition_name: str
    consequence_label: str | None


@dataclass(frozen=True)
class AllegianceBreakResult:
    """A striker's break roll against an allegiance hold (Decision 16)."""

    condition_name: str
    difficulty: int
    strength: int
    resistance: int
    pressure: int
    broke: bool
    ending: AllegianceEnding | None


@dataclass(frozen=True)
class OfferPrice:
    """What accepting an Academy offer costs the learner, for the trainer menu (#4457).

    ``ap`` and ``coppers`` and ``golden_hares`` are what this acceptance charges.
    A skill course the learner is already enrolled in has no coin or Hare left to
    pay (``coppers`` 0, ``golden_hares`` 0) and carries the course's progress in
    ``development_remaining`` / ``development_total``. A skill course not yet
    enrolled charges its coin and one Hare, and its first session's AP, now;
    ``per_session_ap`` is the AP of every session, that first one included.
    ``next_session_next_week`` is True when her open enrollment already ran a
    session this game week, so the next one waits for the week to turn. It only
    changes the menu line, and is not sent on the wire on its own.

    A TRAIN offer charges no AP on acceptance (``ap`` 0): its Hare and coin are paid
    now, and its ``learn_ap_cost`` only sizes the training meter (``training_points``,
    the least it can be: the gift multipliers in ``charge_and_learn`` can raise it).
    The learner pays AP afterwards, session by session, toward that meter, so
    ``per_session_ap`` is None for it.
    """

    ap: int
    coppers: int
    golden_hares: int
    per_session_ap: int | None
    development_remaining: int | None
    development_total: int | None
    training_points: int | None = None
    next_session_next_week: bool = False
