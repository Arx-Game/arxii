"""Cached handlers for items / equipment relationships.

Spec D §3.3. Single load, in-memory cache, explicit invalidation by
mutators (equip/unequip/attach_facet/remove_facet_from_item).

Identity-divergence caveat
--------------------------
Handler invalidation works by mutating state on a specific Python
instance: ``handler._cached = None``. The handler is stored on the
parent (``character.equipped_items`` is a cached_property), so the
mutation only propagates to readers that walk the same Python instance.

SharedMemoryModel's identity map *usually* returns the same instance
for the same pk — but the guarantee is path-dependent. ``ObjectDB.objects.get(pk=X)``
and FK descriptor access (``sheet.character``) go through the identity
map; ``select_related("character")`` on a queryset bypasses it and
materializes a fresh instance.

Practical rule: **never invalidate a handler reached through
``select_related``**. If you fetched a row with
``EquippedItem.objects.select_related("character").get(...)`` and need
to invalidate, refetch the character via
``ObjectDB.objects.get(pk=row.character_id)`` first, or skip
``select_related("character")`` and let lazy FK access go through the
identity map.

See ``services/facets.py`` for an existing comment on the same point.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

from django.db.models import Prefetch
from evennia.objects.models import ObjectDB

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import EquippedItem, ItemFacet, ItemInstance, Outfit
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


class CharacterCarriedItemsHandler:
    """Cached handler for items located on (carried by) a character.

    "Carried" = ``ItemInstance`` rows whose ``game_object.location`` is
    the character — i.e., the character's inventory contents, including
    equipped items (an equipped item's game_object is also located on
    the wearer).

    Mutators (pick up / drop / give / transfer) must call
    ``character.carried_items.invalidate()`` so the next read re-fetches.
    """

    def __init__(self, character: ObjectDB) -> None:
        self._character = character
        self._cached: list[ItemInstance] | None = None

    @property
    def _items(self) -> list[ItemInstance]:
        if self._cached is None:
            from world.items.models import ItemFacet, ItemInstance  # noqa: PLC0415

            qs = (
                ItemInstance.objects.filter(game_object__db_location=self._character)
                .select_related(
                    "template",
                    "quality_tier",
                    "game_object",
                    "image",
                    "template__image",
                )
                .prefetch_related(
                    Prefetch(
                        "item_facets",
                        queryset=ItemFacet.objects.select_related(
                            "facet",
                            "attachment_quality_tier",
                        ),
                        to_attr="cached_item_facets",
                    ),
                )
            )
            self._cached = list(qs)
        return self._cached

    def __iter__(self) -> Iterator[ItemInstance]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def all(self) -> list[ItemInstance]:
        """Return a fresh list of cached items (safe to mutate)."""
        return list(self._items)

    def get(self, pk: int) -> ItemInstance | None:
        """Return the carried item with this pk, or None."""
        for item in self._items:
            if item.pk == pk:
                return item
        return None

    def invalidate(self) -> None:
        self._cached = None


class CharacterSheetOutfitsHandler:
    """Cached handler for a character_sheet's saved outfits.

    Walks ``CharacterSheet.outfits`` reverse relation once and caches
    the list with each outfit's slots prefetched. Mutators
    (save_outfit / delete_outfit / outfit slot edits) must call
    ``sheet.outfits.invalidate()``.
    """

    def __init__(self, sheet: CharacterSheet) -> None:
        self._sheet = sheet
        self._cached: list[Outfit] | None = None

    @property
    def _outfits(self) -> list[Outfit]:
        if self._cached is None:
            from world.items.models import Outfit, OutfitSlot  # noqa: PLC0415

            qs = (
                Outfit.objects.filter(character_sheet=self._sheet)
                .select_related(
                    "character_sheet",
                    "wardrobe",
                    "wardrobe__template",
                )
                .prefetch_related(
                    Prefetch(
                        "slots",
                        queryset=OutfitSlot.objects.select_related(
                            "item_instance",
                            "item_instance__template",
                            "item_instance__quality_tier",
                        ),
                        to_attr="cached_outfit_slots",
                    ),
                )
                .order_by("name")
            )
            self._cached = list(qs)
        return self._cached

    def __iter__(self) -> Iterator[Outfit]:
        return iter(self._outfits)

    def __len__(self) -> int:
        return len(self._outfits)

    def all(self) -> list[Outfit]:
        """Return a fresh list of cached outfits (safe to mutate)."""
        return list(self._outfits)

    def get(self, pk: int) -> Outfit | None:
        """Return the outfit with this pk, or None."""
        for outfit in self._outfits:
            if outfit.pk == pk:
                return outfit
        return None

    def invalidate(self) -> None:
        self._cached = None
