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

    ``amount`` is cumulative: the total of this resonance ever imbued. The caller owns
    ``thread.developed_points`` (the bucket level-ups spend from, which this never
    touches) and calls ``refresh_leading_resonance`` once its writes are done.
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
