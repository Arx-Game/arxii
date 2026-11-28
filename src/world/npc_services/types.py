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
    ``teaching_line`` names the Tradition a skill course's role teaches ("Taught in the
    manner of X", None when it teaches none); ``fit_line`` says what of the learner the
    Tradition fits and that sessions are easier ("Fits your X. Sessions are easier for
    you.", None when nothing fits or the fit eases nothing). ``outsider_line`` is "Your
    Tradition does not teach this. Sessions are harder for you.", set when the course's skill
    is one a Tradition's list governs, the learner's own Tradition does not teach it and
    staff set an extra course difficulty above 0 (#5326); it is separate from ``fit_line``
    because a learner can be an outsider and still have a Gift that fits. All three ride the
    wire under their own names (#4659).

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
    teaching_line: str | None = None
    fit_line: str | None = None
    outsider_line: str | None = None


@dataclass(frozen=True)
class CourseTerms:
    """What one skill course session's check is adjusted by for one student (#5326).

    ``ease`` is the difficulty points a student who fits the trainer's Tradition takes off
    (#4659). ``added_difficulty`` is the points an outsider adds: the student's own Tradition
    does not teach the course's skill. Both are read live at each session, and the roll is at
    the course's difficulty plus ``added_difficulty`` minus ``ease``.
    """

    ease: int = 0
    added_difficulty: int = 0
