"""Tests for the crafting kind registry + facet/style handlers (Task 6, #1031).

Covers:
- ``get_handler(FACET_ATTACH)``: pre_validate raises on capacity/dup; apply creates ItemFacet.
- ``get_handler(STYLE_ATTACH)``: pre_validate raises on capacity/dup; apply creates ItemStyle.
- ``get_handler`` of an unregistered kind raises KeyError.
"""

from django.test import TestCase


class FacetAttachHandlerTests(TestCase):
    """Tests for FacetAttachHandler via the registry."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.items.factories import (
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
        )
        from world.magic.factories import FacetFactory

        cls.account = AccountFactory(username="facet_handler_crafter")
        cls.quality = QualityTierFactory(name="FacetHandlerQ", color_hex="#111111")
        # Template with facet_capacity=1 — one slot only.
        cls.template = ItemTemplateFactory(name="FacetHandlerTpl", facet_capacity=1)
        cls.item = ItemInstanceFactory(template=cls.template, quality_tier=cls.quality)

        cls.facet_a = FacetFactory(name="HandlerFacetA")
        cls.facet_b = FacetFactory(name="HandlerFacetB")

        # Fill the single slot with facet_a so capacity tests fire.
        cls.existing_facet = ItemFacetFactory(
            item_instance=cls.item,
            facet=cls.facet_a,
            attachment_quality_tier=cls.quality,
        )

    def _get_handler(self):
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.registry import get_handler

        return get_handler(CraftingRecipeKind.FACET_ATTACH)

    def test_pre_validate_raises_capacity_exceeded(self) -> None:
        """pre_validate raises FacetCapacityExceeded when item is at capacity."""
        from world.items.exceptions import FacetCapacityExceeded

        handler = self._get_handler()
        with self.assertRaises(FacetCapacityExceeded):
            handler.pre_validate(item_instance=self.item, target=self.facet_b)

    def test_pre_validate_raises_already_attached(self) -> None:
        """pre_validate raises FacetAlreadyAttached when the same facet is already on the item."""
        from world.items.exceptions import FacetAlreadyAttached

        # Fresh item with capacity=2 so capacity doesn't shadow the dup check.
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        tpl = ItemTemplateFactory(name="FacetHandlerDupTpl", facet_capacity=2)
        item = ItemInstanceFactory(template=tpl, quality_tier=self.quality)
        from world.items.factories import ItemFacetFactory

        ItemFacetFactory(
            item_instance=item, facet=self.facet_a, attachment_quality_tier=self.quality
        )
        handler = self._get_handler()
        with self.assertRaises(FacetAlreadyAttached):
            handler.pre_validate(item_instance=item, target=self.facet_a)

    def test_apply_creates_item_facet(self) -> None:
        """apply creates an ItemFacet row at the given quality_tier."""
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
        from world.items.models import ItemFacet

        tpl = ItemTemplateFactory(name="FacetHandlerApplyTpl", facet_capacity=2)
        item = ItemInstanceFactory(template=tpl, quality_tier=self.quality)
        handler = self._get_handler()
        result = handler.apply(
            crafter_account=self.account,
            item_instance=item,
            target=self.facet_a,
            quality_tier=self.quality,
        )
        self.assertIsInstance(result, ItemFacet)
        self.assertEqual(result.facet, self.facet_a)
        self.assertEqual(result.attachment_quality_tier, self.quality)
        self.assertTrue(ItemFacet.objects.filter(pk=result.pk).exists())


class StyleAttachHandlerTests(TestCase):
    """Tests for StyleAttachHandler via the registry."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.items.factories import (
            ItemInstanceFactory,
            ItemStyleFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            StyleFactory,
        )

        cls.account = AccountFactory(username="style_handler_crafter")
        cls.quality = QualityTierFactory(name="StyleHandlerQ", color_hex="#222222")
        # Template with style_capacity=1 — one slot only.
        cls.template = ItemTemplateFactory(name="StyleHandlerTpl", style_capacity=1)
        cls.item = ItemInstanceFactory(template=cls.template, quality_tier=cls.quality)

        cls.style_a = StyleFactory(name="HandlerStyleA")
        cls.style_b = StyleFactory(name="HandlerStyleB")

        # Fill the single slot with style_a.
        cls.existing_style = ItemStyleFactory(
            item_instance=cls.item,
            style=cls.style_a,
            attachment_quality_tier=cls.quality,
        )

    def _get_handler(self):
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.registry import get_handler

        return get_handler(CraftingRecipeKind.STYLE_ATTACH)

    def test_pre_validate_raises_capacity_exceeded(self) -> None:
        """pre_validate raises StyleCapacityExceeded when item is at capacity."""
        from world.items.exceptions import StyleCapacityExceeded

        handler = self._get_handler()
        with self.assertRaises(StyleCapacityExceeded):
            handler.pre_validate(item_instance=self.item, target=self.style_b)

    def test_pre_validate_raises_already_attached(self) -> None:
        """pre_validate raises StyleAlreadyAttached when the same style is already on the item."""
        from world.items.exceptions import StyleAlreadyAttached
        from world.items.factories import ItemInstanceFactory, ItemStyleFactory, ItemTemplateFactory

        # Fresh item with capacity=2 so capacity doesn't shadow the dup check.
        tpl = ItemTemplateFactory(name="StyleHandlerDupTpl", style_capacity=2)
        item = ItemInstanceFactory(template=tpl, quality_tier=self.quality)
        ItemStyleFactory(
            item_instance=item, style=self.style_a, attachment_quality_tier=self.quality
        )
        handler = self._get_handler()
        with self.assertRaises(StyleAlreadyAttached):
            handler.pre_validate(item_instance=item, target=self.style_a)

    def test_apply_creates_item_style(self) -> None:
        """apply creates an ItemStyle row at the given quality_tier."""
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
        from world.items.models import ItemStyle

        tpl = ItemTemplateFactory(name="StyleHandlerApplyTpl", style_capacity=2)
        item = ItemInstanceFactory(template=tpl, quality_tier=self.quality)
        handler = self._get_handler()
        result = handler.apply(
            crafter_account=self.account,
            item_instance=item,
            target=self.style_a,
            quality_tier=self.quality,
        )
        self.assertIsInstance(result, ItemStyle)
        self.assertEqual(result.style, self.style_a)
        self.assertEqual(result.attachment_quality_tier, self.quality)
        self.assertTrue(ItemStyle.objects.filter(pk=result.pk).exists())


class RegistryUnregisteredKindTests(TestCase):
    """Tests for get_handler with an unregistered kind."""

    def test_get_handler_raises_key_error_for_unknown_kind(self) -> None:
        """get_handler raises KeyError when no handler is registered for the given kind."""
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.registry import _HANDLER_REGISTRY, get_handler

        # Temporarily remove FACET_ATTACH from the registry to simulate
        # an unregistered kind without needing a new enum value.
        original = _HANDLER_REGISTRY.pop(CraftingRecipeKind.FACET_ATTACH.value, None)
        try:
            with self.assertRaises(KeyError):
                get_handler(CraftingRecipeKind.FACET_ATTACH)
        finally:
            if original is not None:
                _HANDLER_REGISTRY[CraftingRecipeKind.FACET_ATTACH.value] = original
