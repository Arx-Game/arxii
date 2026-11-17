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


@dataclass(frozen=True)
class HarvestOffer:
    """One Primum a character can extract where she stands.

    ``source`` is ``"place"`` (a lair's stock) or ``"creature"`` (a slain foe). A creature
    offer names the foe in ``opponent_id`` and ``opponent_name``; a place offer leaves them
    empty. ``step_name`` is the step the source reads at now.
    """

    substance_id: int
    substance_name: str
    source: str
    opponent_id: int | None
    opponent_name: str
    step_name: str


@dataclass(frozen=True)
class HarvestResult:
    """What one extract attempt came to.

    ``harvested`` is true when Primum was taken. ``amount_taken`` is the Primum that left the
    source, ``quantity`` the items minted, ``outcome_name`` the rolled outcome ("" when no
    roll was made), ``message`` the sentence the harvester reads.
    """

    harvested: bool
    substance_name: str
    amount_taken: int
    quantity: int
    outcome_name: str
    message: str
