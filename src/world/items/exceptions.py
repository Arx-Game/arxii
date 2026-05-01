"""Typed exceptions for the items app.

Per CLAUDE.md `ViewSet & API Design`: typed exceptions with `user_message`
property + `SAFE_MESSAGES` allowlist for safe API surfacing. View and
inputfunc layers read `exc.user_message` — never `str(exc)`.

Two families share `ItemError` as the base so `except ItemError:` catches
both:

* Data-layer errors raised by `world.items.services.*` for invalid slot,
  facet capacity, etc.
* Inventory action errors raised by `flows.service_functions.inventory.*`
  for permission denial, possession mismatches, container constraints, etc.
"""

from typing import ClassVar


class ItemError(Exception):
    """Base for items typed exceptions."""

    user_message: str = "An items error occurred."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"An items error occurred."})


# ---------------------------------------------------------------------------
# Data-layer errors (slot validity, facet capacity, etc.)
# ---------------------------------------------------------------------------


class SlotConflict(ItemError):
    """Another item already occupies the requested (body_region, equipment_layer) slot."""

    user_message = "Something is already worn there."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"Something is already worn there."})


class SlotIncompatible(ItemError):
    """The item's template does not declare the requested (body_region, equipment_layer)."""

    user_message = "That item cannot be worn there."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That item cannot be worn there."})


class FacetCapacityExceeded(ItemError):
    """The item already carries the maximum number of facets its template allows."""

    user_message = "This item has no remaining facet slots."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"This item has no remaining facet slots."},
    )


class FacetAlreadyAttached(ItemError):
    """That facet is already attached to this item."""

    user_message = "That facet is already attached to this item."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"That facet is already attached to this item."},
    )


# ---------------------------------------------------------------------------
# Inventory action errors (pick_up, drop, give, equip, etc.)
# ---------------------------------------------------------------------------


class InventoryError(ItemError):
    """Base for inventory-action failures (pick_up, drop, give, equip, etc.)."""

    user_message: str = "That action could not be completed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That action could not be completed."})


class PermissionDenied(InventoryError):
    user_message = "You cannot do that with that item."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You cannot do that with that item."})


class NotInPossession(InventoryError):
    user_message = "You are not carrying that."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You are not carrying that."})


class NotEquipped(InventoryError):
    user_message = "You are not wearing that."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You are not wearing that."})


class ContainerFull(InventoryError):
    user_message = "That container is already full."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That container is already full."})


class ContainerClosed(InventoryError):
    user_message = "That container is closed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That container is closed."})


class ItemTooLarge(InventoryError):
    user_message = "That item is too large to fit in there."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"That item is too large to fit in there."},
    )


class NotAContainer(InventoryError):
    user_message = "That isn't a container."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That isn't a container."})


class NoDropLocation(InventoryError):
    user_message = "You have nowhere to drop that."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"You have nowhere to drop that."},
    )


class RecipientNotAdjacent(InventoryError):
    user_message = "They are not here to receive it."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"They are not here to receive it."})


class NotReachable(InventoryError):
    user_message = "You can't reach that."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You can't reach that."})


class NotInContainer(InventoryError):
    user_message = "That isn't in a container."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That isn't in a container."})


class OutfitIncomplete(InventoryError):
    user_message = "Some pieces of that outfit are missing."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"Some pieces of that outfit are missing."},
    )
