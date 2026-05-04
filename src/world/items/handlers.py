"""Cached handlers for items / equipment relationships.

Spec D §3.3. Single load, in-memory cache, explicit invalidation by
mutators (equip/unequip/attach_facet/remove_facet_from_item).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

from django.db.models import Prefetch
from evennia.objects.models import ObjectDB

if TYPE_CHECKING:
    from world.items.models import EquippedItem, ItemFacet
    from world.magic.models import Facet


class CharacterEquipmentHandler:
    """Cached handler for a character's equipped items + their facets.

    One DB load on first access; subsequent reads serve from the cached list.
    Mutators (equip/unequip/attach_facet) invalidate explicitly via
    ``handler.invalidate()``.
    """

    def __init__(self, character: ObjectDB) -> None:
        self._character = character
        self._cached: list[EquippedItem] | None = None

    @property
    def _equipped(self) -> list[EquippedItem]:
        if self._cached is None:
            from world.items.models import EquippedItem, ItemFacet, TemplateSlot  # noqa: PLC0415

            qs = (
                EquippedItem.objects.filter(character=self._character)
                .select_related(
                    "item_instance",
                    "item_instance__template",
                    "item_instance__quality_tier",
                )
                .prefetch_related(
                    Prefetch(
                        "item_instance__item_facets",
                        queryset=ItemFacet.objects.select_related(
                            "facet",
                            "attachment_quality_tier",
                        ),
                        to_attr="cached_item_facets",
                    ),
                    Prefetch(
                        "item_instance__template__slots",
                        queryset=TemplateSlot.objects.all(),
                        to_attr="cached_slots",
                    ),
                )
            )
            self._cached = list(qs)
        return self._cached

    def __iter__(self) -> Iterator[EquippedItem]:
        return iter(self._equipped)

    def iter_item_facets(self) -> Iterable[ItemFacet]:
        for equipped in self._equipped:
            yield from equipped.item_instance.cached_item_facets

    def item_facets_for(self, facet: Facet) -> list[ItemFacet]:
        return [
            item_facet
            for equipped in self._equipped
            for item_facet in equipped.item_instance.cached_item_facets
            if item_facet.facet_id == facet.pk
        ]

    def invalidate(self) -> None:
        self._cached = None
