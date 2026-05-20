"""Typed call-record dataclasses for the integration stub modules.

These exist so the in-memory call logs the stubs expose for tests are
properly typed structured data (never a bare dict). Both records carry the
emitted line's pk so a test can cross-reference back to the
:class:`~world.missions.models.MissionDeedRewardLine` without holding a
reference.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MoneyStubCall:
    """One recorded invocation of :func:`world.missions.integrations.money_stub.deliver_money`.

    ``amount`` is None when the emitted line carried no numeric payout
    (rare for the MONEY sink, but the column is nullable upstream so we
    mirror it). ``recipient_id`` is the line's recipient character pk.
    """

    line_id: int
    recipient_id: int
    amount: int | None
    ref: str


@dataclass(frozen=True)
class BeatStubCall:
    """One recorded invocation of :func:`world.missions.integrations.beat_stub.propagate_beat`.

    Phase 5b.3 will replace this with a real Beat-completion call; the
    recorded shape stays the same so 5b.3's wiring is a drop-in.
    """

    line_id: int
    recipient_id: int
    amount: int | None
    ref: str
