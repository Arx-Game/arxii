"""Shared player-facing price copy for authoring pages (#3675 review round 1).

Promoted out of ``tradition_slate.live.price_text``, which the Distinction
Builder had re-implemented as its own three-way branch - both pages draw the
same "Free"/"Refunds N"/bare-cost copy, so one function backs both.
"""

from __future__ import annotations


def price_text(value: int, *, per_rank: bool = False) -> str:
    """Human copy for a derived price: "Free", "Refunds N", or the cost itself.

    ``per_rank=True`` appends " per rank" to a positive value - the
    Distinction Builder's own price is a rate (``cost_per_rank``), unlike the
    tradition slate page's already-resolved per-line price, which is always
    a plain number.
    """
    if value == 0:
        return "Free"  # noqa: STRING_LITERAL - player-facing copy, not an identifier
    if value < 0:
        return f"Refunds {abs(value)}"
    if per_rank:
        return f"{value} per rank"
    return str(value)
