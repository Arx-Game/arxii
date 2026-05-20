"""In-memory money-delivery stub (Phase 5b.1 placeholder).

The real money ledger does not yet exist. Until then, the missions reward
router calls :func:`deliver_money` for every IMMEDIATE/MONEY emitted line;
this module appends a :class:`MoneyStubCall` to an in-memory list so tests
can verify the call fired.

Tests SHOULD call :func:`clear_calls` in ``setUp`` because the call log is
module-level and persists across tests in the same process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.missions.integrations.types import MoneyStubCall

if TYPE_CHECKING:
    from world.missions.models import MissionDeedRewardLine


_MONEY_CALLS: list[MoneyStubCall] = []


def deliver_money(line: MissionDeedRewardLine) -> None:
    """Record one IMMEDIATE/MONEY delivery call.

    No DB write — the real ledger isn't built yet (Phase 6+ work). The
    recorded :class:`MoneyStubCall` carries the line pk so tests can
    cross-reference without holding the ``MissionDeedRewardLine`` itself.
    """
    _MONEY_CALLS.append(
        MoneyStubCall(
            line_id=line.pk,
            recipient_id=line.recipient_id,
            amount=line.amount,
            ref=line.ref,
        )
    )


def get_calls() -> tuple[MoneyStubCall, ...]:
    """An immutable snapshot of the recorded calls (tuple, not list)."""
    return tuple(_MONEY_CALLS)


def clear_calls() -> None:
    """Empty the recorded-call log (call in ``setUp`` for isolation)."""
    _MONEY_CALLS.clear()
