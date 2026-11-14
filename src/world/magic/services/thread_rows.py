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
        thread.save(update_fields=["resonance"])
    return leading.resonance
