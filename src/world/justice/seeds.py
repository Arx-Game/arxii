"""Placeholder per-society sentence-ladder seed data (#2378 Task 4).

Not auto-invoked — staff/tests call :func:`seed_placeholder_sentence_ladders`
directly. Seed data in this codebase flows through Django's fixture system
(never a management command), but the real per-society ladders are a content
pass's job (spec #2378 §8); this helper just materializes PLACEHOLDER rows so
the ladder consult has something to read before that pass lands.
"""

from __future__ import annotations

from world.justice.constants import SentenceKind
from world.justice.models import SentenceLadderRung
from world.societies.models import Society

# PLACEHOLDER per-society ladders (content pass owns the real rows, spec #2378 §8).
_PLACEHOLDER_LADDERS: dict[str, tuple[tuple[int, str], ...]] = {
    "Umbros": (
        (0, SentenceKind.BRIG_TERM),
        (1, SentenceKind.EXILE),
        (2, SentenceKind.ARENA_TRIAL),
    ),
    "Inferna": (
        (0, SentenceKind.CONFISCATION),
        (1, SentenceKind.EXILE),
        (2, SentenceKind.EXECUTION),
    ),
}


def seed_placeholder_sentence_ladders() -> int:
    """Write placeholder sentence-ladder rungs for Umbros and Inferna, if present.

    Looks each society up by exact name (``Society.objects.filter(name=name).first()``)
    and skips it gracefully when absent — the content pass owns the real rows.
    ``update_or_create`` keyed on (society, level) so re-runs update the existing
    row rather than duplicate or raise on the unique constraint. Returns the
    number of rungs written (0 when neither society exists).
    """
    written = 0
    for name, rungs in _PLACEHOLDER_LADDERS.items():
        society = Society.objects.filter(name=name).first()
        if society is None:
            continue
        for level, kind in rungs:
            SentenceLadderRung.objects.update_or_create(
                society=society,
                level=level,
                defaults={"sentence_kind": kind, "flavor": "PLACEHOLDER"},
            )
            written += 1
    return written
