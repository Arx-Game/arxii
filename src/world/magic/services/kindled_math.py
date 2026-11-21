"""The pure arithmetic of kindled strength (#5231), shared by the pull and the cast.

Two small rules that a pull's payer options and a cast's resonance options both apply, written
once so the two screens can never disagree: how an affinity's staff-set boost scales a
strength's number, and which one option is marked stronger.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models import Resonance


def scale_by_kindled_boost(resonance: Resonance, amount: int) -> int:
    """``amount`` scaled by ``resonance``'s affinity's ``kindled_boost_percent``, rounded down.

    The one scaling of a kindled strength's number: the pull levels it adds to a thread's read
    and the power it adds to a cast both go through here, so an Abyssal resonance can pay more
    than a Primal one at the same strength row.
    """
    return amount * resonance.affinity.kindled_boost_percent // 100


def stronger_marks(strengths: Sequence[int | None], baselines: Sequence[int]) -> list[bool]:
    """Which entry, if any, is marked stronger: a list of flags, at most one of them true.

    An entry is marked when its strength is the single highest of the list and strictly above
    its own baseline: the default entry's strength for a cast's options, each payer's own
    unboosted read for a pull's. A tie for the highest marks none. An entry whose strength is
    ``None`` does not compete (a payer that brings no perks) and is never marked.
    """
    competing = {i: strength for i, strength in enumerate(strengths) if strength is not None}
    top = max(competing.values(), default=0)
    leaders = [i for i, strength in competing.items() if strength == top]
    stronger = leaders[0] if len(leaders) == 1 and top > baselines[leaders[0]] else None
    return [i == stronger for i in range(len(strengths))]
