"""Work out a modifier row's derived amount (#4878).

``derived_amount(sheet, row, per_step)`` is the one computation every row with the shared
menu (``DerivedAmountMixin``) uses: the row's per-step amount times the input divided by
the row's step, held at its cap. Read at evaluation time, never stored.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

from world.mechanics.constants import AmountInput

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.mechanics.derived_amount_models import DerivedAmountMixin


def derived_amount(sheet: CharacterSheet | None, row: DerivedAmountMixin, per_step: int) -> int:
    """``per_step`` times the input's whole steps for ``sheet``, held at the row's cap.

    The sign is the per-step amount's; the cap is a magnitude. No sheet, no input: 0 steps.
    """
    steps = input_value(sheet, row) // row.amount_per
    total = per_step * steps
    if row.amount_cap is not None and abs(total) > row.amount_cap:
        return row.amount_cap if total > 0 else -row.amount_cap
    return total


def input_value(sheet: CharacterSheet | None, row: DerivedAmountMixin) -> int:
    """The row's input for ``sheet``, never below 0."""
    if sheet is None:
        return 0
    if row.amount_input == AmountInput.CHARACTER_LEVEL:
        return max(0, sheet.current_level or 0)
    if row.amount_input == AmountInput.THREAD_LEVEL:
        return _thread_level(sheet, row)
    if row.amount_input == AmountInput.CHECK_RANK:
        return _check_rank(sheet, row)
    return 0


def _thread_level(sheet: CharacterSheet, row: DerivedAmountMixin) -> int:
    """The shown level of the holder's highest thread on the row's trait or facet.

    A character holds one thread per resonance on an anchor, so the highest one counts.
    No thread there: 0.
    """
    from django.db.models import Max  # noqa: PLC0415

    from world.magic.models import Thread  # noqa: PLC0415
    from world.magic.services.threads import shown_thread_level  # noqa: PLC0415

    threads = Thread.objects.filter(owner=sheet)
    if row.amount_thread_trait_id is not None:
        threads = threads.filter(target_trait_id=row.amount_thread_trait_id)
    else:
        threads = threads.filter(target_facet_id=row.amount_thread_facet_id)
    stored = threads.aggregate(level=Max("level"))["level"]
    return shown_thread_level(stored) if stored else 0


# The (sheet, check type) ratings being read right now. A check-rank row that the rating it
# reads would count again (a stat target authored past ``clean()``, by fixture or a later
# recategorisation) reads 0 the second time instead of recursing.
_RATINGS_IN_PROGRESS: ContextVar[frozenset[tuple[int, int]]] = ContextVar(
    "derived_amount_ratings_in_progress", default=frozenset()
)


def _check_rank(sheet: CharacterSheet, row: DerivedAmountMixin) -> int:
    """The holder's rank on the row's check, from its rating with no roll; at least 0."""
    from world.checks.services import compute_check_rating  # noqa: PLC0415
    from world.traits.models import CheckRank  # noqa: PLC0415

    character = sheet.character
    key = (sheet.pk, row.amount_check_type_id)
    in_progress = _RATINGS_IN_PROGRESS.get()
    if character is None or key in in_progress:
        return 0
    token = _RATINGS_IN_PROGRESS.set(in_progress | {key})
    try:
        points = compute_check_rating(character, row.amount_check_type)
    finally:
        _RATINGS_IN_PROGRESS.reset(token)
    rank = CheckRank.get_rank_for_points(points)
    return max(0, rank.rank) if rank is not None else 0
