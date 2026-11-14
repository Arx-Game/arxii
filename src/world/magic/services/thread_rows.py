"""The resonance rows of a Thread, and its leading resonance (#5123).

A thread holds several resonances on its ``ThreadResonance`` rows. ``Thread.resonance`` is
a denormalized copy of the leading one (the first row by the rows' Meta ordering: largest
amount, ties to the row created first). ``refresh_leading_resonance`` is its only writer;
every service that writes rows calls it afterwards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.models.threads import ThreadResonance

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.magic.models import Resonance, Thread


def refresh_leading_resonance(thread: Thread) -> Resonance:
    """Point ``thread.resonance`` at its leading row's resonance; save only if it changed.

    Raises ``ValueError`` when the thread has no resonance rows: a thread always holds
    at least one.
    """
    leading = (
        ThreadResonance.objects.filter(thread=thread)
        .select_related("resonance")
        .order_by(*ThreadResonance._meta.ordering)  # noqa: SLF001 - the ordering is the rule
        .first()
    )
    if leading is None:
        msg = f"Thread {thread.pk} has no resonance rows."
        raise ValueError(msg)
    if thread.resonance_id != leading.resonance_id:
        thread.resonance = leading.resonance
        thread.save(update_fields=["resonance", "updated_at"])
    return leading.resonance


def add_to_resonance_row(thread: Thread, resonance: Resonance, amount: int) -> ThreadResonance:
    """Add ``amount`` points to ``resonance``'s row on ``thread``, creating the row if needed.

    Writes the row only: the caller owns ``thread.developed_points`` (the rows' amounts sum
    to it) and calls ``refresh_leading_resonance`` once its writes are done.
    """
    row, _created = ThreadResonance.objects.get_or_create(thread=thread, resonance=resonance)
    if amount:
        row.amount += amount
        row.save(update_fields=["amount"])
    return row


def write_resonance_rows(thread: Thread, resonances: Sequence[Resonance]) -> None:
    """Write a row at zero for each of ``resonances``, in the order given (earliest leads a tie).

    A resonance the thread already holds keeps its row. The caller refreshes the leading
    resonance afterwards.
    """
    for resonance in resonances:
        ThreadResonance.objects.get_or_create(thread=thread, resonance=resonance)


def consume_row_points(thread: Thread, spent: int) -> None:
    """Take ``spent`` points out of the rows, in proportion to what each holds.

    Raising a level spends development points; the rows' amounts sum to the thread's
    ``developed_points``, so the rows pay the same total. Each row pays its share rounded
    down, and the remainder goes one point at a time to the rows with the largest
    fractions (ties to the row first in order), so the rows' sum drops by exactly
    ``spent`` and the mix keeps its shape. The caller refreshes the leading resonance.
    """
    if spent <= 0:
        return
    rows = list(ThreadResonance.objects.filter(thread=thread))
    total = sum(row.amount for row in rows)
    spent = min(spent, total)
    if spent == 0:
        return
    shares = [divmod(spent * row.amount, total) for row in rows]
    left = spent - sum(whole for whole, _fraction in shares)
    order = sorted(range(len(rows)), key=lambda i: -shares[i][1])
    extra = set(order[:left])
    for index, row in enumerate(rows):
        row.amount -= shares[index][0] + (1 if index in extra else 0)
        row.save(update_fields=["amount"])
