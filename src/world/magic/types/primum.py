"""Primum power line types (#5125).

``SourcePoints`` is one source of Primum a cast draws on: a place's stock of a substance, or an
item the caster carries. Nothing here is stored.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourcePoints:
    """One source of Primum and the signed points it is worth to this caster.

    ``kind`` is a ``PrimumLineKind`` value. ``label`` is already redacted for what the caster
    has perceived (an opposing substance she has not sensed reads ``Something here works against
    your ice``). ``points`` is negative when the source works against the caster's substance.
    ``item_id`` is set only for an item source.
    """

    kind: str
    label: str
    points: int
    substance_id: int
    item_id: int | None = None
