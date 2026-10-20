"""The item admin's rail: what an item means to its current holder (#4512, #4462).

Read-only and computed from the records by ``item_meaning``; staff never type it. It is
for staff looking at one item, so it names the signals and their points. The players in
a room never see either (examine credits people, never points).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.items.constants import MeaningSignalKind
from world.items.services.meaning import item_meaning

if TYPE_CHECKING:
    from world.items.models import ItemInstance


@dataclass(frozen=True)
class RailLine:
    label: str
    detail: str
    points: int


@dataclass(frozen=True)
class MeaningRail:
    holder: str
    lines: tuple[RailLine, ...]
    total: int
    note: str
    made_from_cap: int = 0


def meaning_rail(item: ItemInstance) -> MeaningRail | None:
    """The signals that make ``item`` matter to its current holder, or None if nobody
    holds it (a destroyed or given-up piece means nothing to anyone)."""
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    holder = item.holder_character_sheet
    if holder is None:
        return None
    meaning = item_meaning(item, holder, config=get_devotion_config())
    labels = {str(value): str(label) for value, label in MeaningSignalKind.choices}
    lines = tuple(
        RailLine(labels.get(signal.kind, signal.kind), signal.detail, signal.points)
        for signal in meaning.signals
    )
    persona = holder.primary_persona
    note = "Computed from the records beside it; staff do not type it."
    return MeaningRail(
        holder=persona.name if persona is not None else str(holder),
        lines=lines,
        total=meaning.points,
        note=note,
        made_from_cap=get_devotion_config().made_from_max_points,
    )
