"""Typed exceptions for the items app.

Per CLAUDE.md `ViewSet & API Design`: typed exceptions with `user_message`
property + `SAFE_MESSAGES` allowlist for safe API surfacing.
"""

from typing import ClassVar


class ItemError(Exception):
    """Base for items typed exceptions."""

    user_message: str = "An items error occurred."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"An items error occurred."})


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
