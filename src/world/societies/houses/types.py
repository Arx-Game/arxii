"""Founder claim payload shapes (#3983 Plan B).

The kin and land rows a CG founder writes before staff review, carried from
the (Task 3) serializer into ``submit_house_claim`` and stored as
``HouseClaimKin``/``HouseClaimLand`` rows. Plain frozen dataclasses — no
model imports needed, so this stays a cheap shape to construct from request
data without touching the ORM.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimKinDraft:
    """One person the founder writes into the house before finalize."""

    name: str
    relation: str
    gender_id: int | None = None
    age: int | None = None
    is_deceased: bool = False
    born_into_id: int | None = None
    basis: str = ""
    is_household: bool = False


@dataclass(frozen=True)
class ClaimLandDraft:
    """The founder's writing for one rung of the claimed seat chain."""

    title_id: int
    land_name: str = ""
    description: str = ""
    hall_name: str = ""
    land_shape_names: tuple[str, ...] = ()
