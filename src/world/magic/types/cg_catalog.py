"""Result types for the CG gift/technique availability service (#2426)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models.techniques import Technique


@dataclass(frozen=True)
class TechniqueOptions:
    """Availability pool for one (path, gift, tradition) combination during CG.

    ``pool`` and ``tradition`` both come from the path's list for the gift
    (``PathGiftGrant.starter_techniques``, #4555): ``pool`` holds the techniques no
    Tradition grant lists, ``tradition`` the ones this tradition's grant
    (``TraditionGiftGrant.special_techniques``) lists, so the two never overlap.
    ``species`` contains techniques belonging to the selected species' granted
    gifts. Callers treat availability as the union of all three.
    """

    pool: list[Technique] = field(default_factory=list)
    tradition: list[Technique] = field(default_factory=list)
    species: list[Technique] = field(default_factory=list)


@dataclass(frozen=True)
class GiftOfferings:
    """Which Tradition and Path pairings offer a new character a Major Gift (#5197).

    One read of the whole catalog, by the rule ``get_gift_options`` applies to a single
    pairing: a Major Gift is offered when the Path's list for it holds a technique a new
    character can take that is open to the Tradition. Character creation marks a Path or a
    Tradition "Not Yet Implemented" from ``pairs``, and the Required content dashboard
    reports ``hidden`` and the pairings missing from ``pairs``, so the page and the
    dashboard cannot disagree.

    ``pairs`` holds ``(tradition id, path id)`` for every pairing that offers at least one
    gift. ``hidden`` holds ``(path id, gift id)`` for every Major Gift a Path offers to no
    active Tradition. ``paths``, ``gifts`` and ``tradition_ids`` are what was read: the
    active Prospect Paths and the Major Gifts as ``(id, name)``, and the active Traditions.
    """

    pairs: frozenset[tuple[int, int]]
    hidden: tuple[tuple[int, int], ...]
    paths: tuple[tuple[int, str], ...]
    gifts: tuple[tuple[int, str], ...]
    tradition_ids: tuple[int, ...]

    def offers(self, tradition_id: int, path_id: int) -> bool:
        """Whether a member of the Tradition is offered any gift on the Path."""
        return (tradition_id, path_id) in self.pairs

    def path_offers_under(self, path_id: int, tradition_ids: Iterable[int]) -> bool:
        """Whether the Path offers a gift under at least one of the Traditions."""
        return any((tradition_id, path_id) in self.pairs for tradition_id in tradition_ids)

    def tradition_offers_on_some_path(self, tradition_id: int) -> bool:
        """Whether the Tradition is offered a gift on any Path at all."""
        return any(pair[0] == tradition_id for pair in self.pairs)
