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


def payer_level_read(thread: Thread, payer: Resonance) -> int | None:
    """The thread level ``payer``'s perks are read at when it pays a pull, or ``None`` (#5123).

    The leading resonance reads the thread's own level. Another resonance the thread holds
    a row for reads ``second_resonance_level_step`` levels lower, but never so low that its
    multiplier would beat the leader's (``thread_level_multiplier`` is not monotonic below
    level 10: 1 at level 0, 0.1 at level 1), in which case it reads the leader's level.
    A resonance the thread holds no row for gets ``None``: it pays, and brings no perks.
    """
    from world.magic.services.drift import get_drift_config  # noqa: PLC0415
    from world.magic.services.threads import thread_level_multiplier  # noqa: PLC0415

    if payer.pk == thread.resonance_id:
        return thread.level
    held = thread.owner.character.threads.resonances_of(thread)
    if all(resonance.pk != payer.pk for resonance in held):
        return None
    candidate = max(0, thread.level - get_drift_config().second_resonance_level_step)
    if thread_level_multiplier(candidate) <= thread_level_multiplier(thread.level):
        return candidate
    return thread.level
