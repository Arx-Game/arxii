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
    ``item_id`` is set only for an item source. ``label`` is the power ledger's line;
    ``card_label`` is the cast card's line for the same source (the room and step, or the
    item), already redacted the same way. ``relation`` is a ``SubstanceRelationKind`` value, or
    ``""`` when the source is the caster's own substance. ``hidden`` marks a source of another
    substance she has not perceived (related or opposed), which the card shows only as power.
    """

    kind: str
    label: str
    points: int
    substance_id: int
    item_id: int | None = None
    card_label: str = ""
    relation: str = ""
    hidden: bool = False


@dataclass(frozen=True)
class HarvestOffer:
    """One Primum a character can extract where she stands.

    ``source`` is ``"place"`` (a lair's stock) or ``"creature"`` (a slain foe). A creature
    offer names the foe in ``opponent_id`` and ``opponent_name``; a place offer leaves them
    empty. ``step_name`` is the step the source reads at now. ``check_name`` is the name of
    the harvest check she rolls ("" while none is set).
    """

    substance_id: int
    substance_name: str
    source: str
    opponent_id: int | None
    opponent_name: str
    step_name: str
    check_name: str = ""


@dataclass(frozen=True)
class HarvestResult:
    """What one extract attempt came to.

    ``harvested`` is true when Primum was taken. ``amount_taken`` is the Primum that left the
    source, ``quantity`` the items minted, ``outcome_name`` the rolled outcome ("" when no
    roll was made), ``message`` the sentence the harvester reads, ``remaining_line`` one
    sentence on what the source holds now ("" when nothing changed).
    """

    harvested: bool
    substance_name: str
    amount_taken: int
    quantity: int
    outcome_name: str
    message: str
    remaining_line: str = ""


@dataclass(frozen=True)
class PrimumSense:
    """One substance a character senses in the place she stands, and the step it reads at."""

    substance_id: int
    substance_name: str
    step_name: str
