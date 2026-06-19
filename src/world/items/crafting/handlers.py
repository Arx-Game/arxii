"""Crafting handler ABC and concrete implementations.

``CraftingHandler`` is the abstract base for kind-specific crafting logic.
Each concrete handler implements:

- ``pre_validate`` — raise typed exceptions before a roll is wasted.
- ``apply`` — create and return the attachment row.

Both concrete handlers are registered at module import time so that
``get_handler(CraftingRecipeKind.FACET_ATTACH)`` works as soon as
``world.items.crafting`` is imported.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.items.models import ItemFacet, ItemInstance, ItemStyle, QualityTier


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class CraftingHandler(ABC):
    """Protocol for crafting kind handlers (abstract base class)."""

    @abstractmethod
    def pre_validate(self, *, item_instance: ItemInstance, target: object) -> None:
        """Raise a typed exception if the attachment is invalid.

        Called before any roll so that a full/duplicate item never wastes
        a crafting attempt.

        Args:
            item_instance: The item that will receive the attachment.
            target: The Facet or Style to be attached.

        Raises:
            FacetAlreadyAttached: The facet is already on the item.
            FacetCapacityExceeded: The item is at its facet capacity.
            StyleAlreadyAttached: The style is already on the item.
            StyleCapacityExceeded: The item is at its style capacity.
        """

    @abstractmethod
    def apply(
        self,
        *,
        crafter_account: AccountDB,
        item_instance: ItemInstance,
        target: object,
        quality_tier: QualityTier,
    ) -> object:
        """Create and return the attachment row.

        Args:
            crafter_account: The account performing the attachment.
            item_instance: The item receiving the attachment.
            target: The Facet or Style to attach.
            quality_tier: The QualityTier at which the attachment is made.

        Returns:
            The newly created ItemFacet or ItemStyle row.
        """


# ---------------------------------------------------------------------------
# Concrete handlers
# ---------------------------------------------------------------------------


class FacetAttachHandler(CraftingHandler):
    """Handler for ``CraftingRecipeKind.FACET_ATTACH``."""

    def pre_validate(self, *, item_instance: ItemInstance, target: object) -> None:
        from world.items.services.facets import assert_facet_attachable  # noqa: PLC0415

        assert_facet_attachable(item_instance, target)  # type: ignore[arg-type]

    def apply(
        self,
        *,
        crafter_account: AccountDB,
        item_instance: ItemInstance,
        target: object,
        quality_tier: QualityTier,
    ) -> ItemFacet:
        from world.items.services.facets import attach_facet_to_item  # noqa: PLC0415

        return attach_facet_to_item(
            crafter=crafter_account,
            item_instance=item_instance,
            facet=target,  # type: ignore[arg-type]
            attachment_quality_tier=quality_tier,
        )


class StyleAttachHandler(CraftingHandler):
    """Handler for ``CraftingRecipeKind.STYLE_ATTACH``."""

    def pre_validate(self, *, item_instance: ItemInstance, target: object) -> None:
        from world.items.services.styles import assert_style_attachable  # noqa: PLC0415

        assert_style_attachable(item_instance, target)  # type: ignore[arg-type]

    def apply(
        self,
        *,
        crafter_account: AccountDB,
        item_instance: ItemInstance,
        target: object,
        quality_tier: QualityTier,
    ) -> ItemStyle:
        from world.items.services.styles import attach_style_to_item  # noqa: PLC0415

        return attach_style_to_item(
            crafter=crafter_account,
            item_instance=item_instance,
            style=target,  # type: ignore[arg-type]
            attachment_quality_tier=quality_tier,
        )


# ---------------------------------------------------------------------------
# Registration — runs at import time
# ---------------------------------------------------------------------------

from world.items.crafting.constants import CraftingRecipeKind  # noqa: E402
from world.items.crafting.registry import register  # noqa: E402

register(CraftingRecipeKind.FACET_ATTACH, FacetAttachHandler())
register(CraftingRecipeKind.STYLE_ATTACH, StyleAttachHandler())
