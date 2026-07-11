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
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.items.models import ItemFacet, ItemInstance, ItemStyle, QualityTier, Style
    from world.magic.models import Facet

from world.items.exceptions import ItemError

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class CraftingHandler(ABC):
    """Protocol for crafting kind handlers (abstract base class)."""

    @abstractmethod
    def pre_validate(
        self,
        *,
        item_instance: ItemInstance | None,
        target: object,
        output_overrides: dict | None = None,
    ) -> None:
        """Raise a typed exception if the attachment is invalid.

        Called before any roll so that a full/duplicate item never wastes
        a crafting attempt.

        Args:
            item_instance: The item that will receive the attachment (None for ITEM_CREATE).
            target: The Facet or Style to be attached (None for ITEM_CREATE).
            output_overrides: Optional dict for ITEM_CREATE (output_template,
                custom_name, custom_description). Attach handlers ignore this.

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
        item_instance: ItemInstance | None,
        target: object,
        quality_tier: QualityTier,
        output_overrides: dict | None = None,
    ) -> object:
        """Create and return the attachment row (or new ItemInstance for ITEM_CREATE).

        Args:
            crafter_account: The account performing the attachment.
            item_instance: The item receiving the attachment (None for ITEM_CREATE).
            target: The Facet or Style to attach (None for ITEM_CREATE).
            quality_tier: The QualityTier at which the attachment is made.
            output_overrides: Optional dict for ITEM_CREATE (output_template,
                custom_name, custom_description, crafter_character). Attach
                handlers ignore this.

        Returns:
            The newly created ItemFacet, ItemStyle, or ItemInstance row.
        """


# ---------------------------------------------------------------------------
# Concrete handlers
# ---------------------------------------------------------------------------


class FacetAttachHandler(CraftingHandler):
    """Handler for ``CraftingRecipeKind.FACET_ATTACH``."""

    def pre_validate(
        self,
        *,
        item_instance: ItemInstance | None,
        target: object,
        output_overrides: dict | None = None,  # noqa: ARG002
    ) -> None:
        from world.items.services.facets import assert_facet_attachable  # noqa: PLC0415

        assert item_instance is not None  # noqa: S101  # attach handlers always receive a real item
        assert_facet_attachable(item_instance, cast("Facet", target))

    def apply(
        self,
        *,
        crafter_account: AccountDB,
        item_instance: ItemInstance | None,
        target: object,
        quality_tier: QualityTier,
        output_overrides: dict | None = None,  # noqa: ARG002
    ) -> ItemFacet:
        from world.items.services.facets import attach_facet_to_item  # noqa: PLC0415

        assert item_instance is not None  # noqa: S101  # attach handlers always receive a real item
        return attach_facet_to_item(
            crafter=crafter_account,
            item_instance=item_instance,
            facet=cast("Facet", target),
            attachment_quality_tier=quality_tier,
        )


class StyleAttachHandler(CraftingHandler):
    """Handler for ``CraftingRecipeKind.STYLE_ATTACH``."""

    def pre_validate(
        self,
        *,
        item_instance: ItemInstance | None,
        target: object,
        output_overrides: dict | None = None,  # noqa: ARG002
    ) -> None:
        from world.items.services.styles import assert_style_attachable  # noqa: PLC0415

        assert item_instance is not None  # noqa: S101  # attach handlers always receive a real item
        assert_style_attachable(item_instance, cast("Style", target))

    def apply(
        self,
        *,
        crafter_account: AccountDB,
        item_instance: ItemInstance | None,
        target: object,
        quality_tier: QualityTier,
        output_overrides: dict | None = None,  # noqa: ARG002
    ) -> ItemStyle:
        from world.items.services.styles import attach_style_to_item  # noqa: PLC0415

        assert item_instance is not None  # noqa: S101  # attach handlers always receive a real item
        return attach_style_to_item(
            crafter=crafter_account,
            item_instance=item_instance,
            style=cast("Style", target),
            attachment_quality_tier=quality_tier,
        )


class ItemCreateHandler(CraftingHandler):
    """Handler for ``CraftingRecipeKind.ITEM_CREATE`` — mints a new ItemInstance.

    Unlike the attach handlers, ``apply`` creates a new ``ItemInstance`` from the
    recipe's ``output_item_template`` rather than modifying a pre-existing one.
    The instance carries the crafter's provenance (character sheet + persona),
    player-authored custom name/description, the resolved quality tier, and a
    ``OwnershipEvent.CREATED`` ledger entry. The physical ``ObjectDB`` is
    materialized so the item appears in the crafter's inventory immediately.
    """

    def pre_validate(
        self,
        *,
        item_instance: ItemInstance | None,  # noqa: ARG002
        target: object,  # noqa: ARG002
        output_overrides: dict | None = None,
    ) -> None:
        if output_overrides is None:
            return
        template = output_overrides.get("output_template")
        if template is None:
            return
        if not template.is_active:
            raise ItemError("That template is no longer available.")  # noqa: TRY003, EM101
        if not template.is_craftable:
            raise ItemError("That item cannot be crafted.")  # noqa: TRY003, EM101

    def apply(
        self,
        *,
        crafter_account: AccountDB,  # noqa: ARG002
        item_instance: ItemInstance | None,  # noqa: ARG002
        target: object,  # noqa: ARG002
        quality_tier: QualityTier,
        output_overrides: dict | None = None,
    ) -> ItemInstance:
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
        from world.items.constants import OwnershipEventType  # noqa: PLC0415
        from world.items.models import (  # noqa: PLC0415
            ItemInstance as _ItemInstance,
            OwnershipEvent,
        )
        from world.items.services.materialize import materialize_item_game_object  # noqa: PLC0415

        overrides = output_overrides or {}
        output_template = overrides.get("output_template")
        custom_name = overrides.get("custom_name", "")
        custom_description = overrides.get("custom_description", "")
        crafter_character = overrides.get("crafter_character")
        crafter_sheet = CharacterSheet.objects.get(character=crafter_character)
        active_persona = crafter_sheet.primary_persona

        instance = _ItemInstance.objects.create(
            template=output_template,
            quality_tier=quality_tier,
            custom_name=custom_name,
            custom_description=custom_description,
            holder_character_sheet=crafter_sheet,
            crafter_character_sheet=crafter_sheet,
            crafter_persona_display=active_persona,
        )
        OwnershipEvent.objects.create(
            item_instance=instance,
            event_type=OwnershipEventType.CREATED,
            to_character_sheet=crafter_sheet,
            to_persona_display=active_persona,
        )
        materialize_item_game_object(instance, crafter_sheet)
        return instance


# ---------------------------------------------------------------------------
# Registration — runs at import time
# ---------------------------------------------------------------------------

from world.items.crafting.constants import CraftingRecipeKind  # noqa: E402
from world.items.crafting.registry import register  # noqa: E402

register(CraftingRecipeKind.FACET_ATTACH, FacetAttachHandler())
register(CraftingRecipeKind.STYLE_ATTACH, StyleAttachHandler())
register(CraftingRecipeKind.ITEM_CREATE, ItemCreateHandler())
