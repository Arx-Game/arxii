"""Tests for fashion_outfit_bonus service function (#513).

Mirrors the shape of test_services_facets.py and test_resonance_integration.py.
All cases use a real Character wearing a real EquippedItem that carries an
ItemFacet — the same setup pattern as the sibling facet-service tests.
"""

from django.test import TestCase

from world.items.constants import FASHION_MATCH_BASE, BodyRegion, EquipmentLayer
from world.mechanics.services import fashion_outfit_bonus


class FashionOutfitBonusZeroWhenNoStyleTests(TestCase):
    """Case 1: society with current_fashion_style=None returns 0."""

    def test_zero_when_society_has_no_current_style(self) -> None:
        from world.mechanics.factories import ModifierTargetFactory
        from world.societies.factories import SocietyFactory

        society = SocietyFactory(current_fashion_style=None)
        target = ModifierTargetFactory()

        # Lightweight duck-typed sheet stub — function only reads sheet.character
        # after the early-exit guard, which fires first on style=None.
        class _FakeSheet:
            character = None

        result = fashion_outfit_bonus(_FakeSheet(), target, society)
        self.assertEqual(result, 0)


class FashionOutfitBonusHappyPathTests(TestCase):
    """Cases 2-5: happy path + edge cases with a real character + equipped item."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.items.factories import (
            EquippedItemFactory,
            FashionStyleBonusFactory,
            FashionStyleFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            TemplateSlotFactory,
        )
        from world.magic.factories import FacetFactory
        from world.mechanics.factories import ModifierTargetFactory
        from world.societies.factories import SocietyFactory

        # Quality tier with stat_multiplier = 1.0 (Common / unit multiplier).
        cls.quality = QualityTierFactory(name="Common", stat_multiplier=1.0)

        # Facet that IS in vogue and one that is NOT.
        cls.facet_in = FacetFactory(name="FashionFacetIn")
        cls.facet_out = FacetFactory(name="FashionFacetOut")

        # Item template + slot so EquippedItemFactory can assign body_region/layer.
        cls.template = ItemTemplateFactory(name="FashionTestItem")
        TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # Item instance with quality tier (item_mult = 1.0).
        cls.item = ItemInstanceFactory(template=cls.template, quality_tier=cls.quality)

        # ItemFacet attaching facet_in to the item (attach_mult = 1.0).
        cls.item_facet = ItemFacetFactory(
            item_instance=cls.item,
            facet=cls.facet_in,
            attachment_quality_tier=cls.quality,
        )

        # Character wearing the item.
        cls.character = CharacterFactory(db_key="FashionBonusChar")
        cls.equipped = EquippedItemFactory(
            character=cls.character,
            item_instance=cls.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # CharacterSheet duck — fashion_outfit_bonus only reads sheet.character.
        class _SheetStub:
            character = cls.character

        cls.sheet = _SheetStub()

        # ModifierTarget used in bonus rows.
        cls.target = ModifierTargetFactory(name="FashionTarget")
        cls.other_target = ModifierTargetFactory(name="OtherTarget")

        # FashionStyle with facet_in in vogue.
        cls.style = FashionStyleFactory(name="CurrentStyle")
        cls.style.in_vogue_facets.add(cls.facet_in)

        # FashionStyleBonus weight=1 (cases 2 and 4).
        cls.bonus_w1 = FashionStyleBonusFactory(
            fashion_style=cls.style, target=cls.target, weight=1
        )

        # Society pointing at the style.
        cls.society = SocietyFactory(name="FashionSociety", current_fashion_style=cls.style)

    def test_happy_path_common_item_and_attachment_returns_base(self) -> None:
        """Case 2: item_mult=1.0, attach_mult=1.0, weight=1 → FASHION_MATCH_BASE."""
        result = fashion_outfit_bonus(self.sheet, self.target, self.society)
        self.assertEqual(result, FASHION_MATCH_BASE)

    def test_weight_doubles_bonus(self) -> None:
        """Case 3: weight=2 → bonus == 2 × FASHION_MATCH_BASE."""
        from world.items.factories import FashionStyleBonusFactory
        from world.mechanics.factories import ModifierTargetFactory

        doubled_target = ModifierTargetFactory(name="DoubledTarget")
        FashionStyleBonusFactory(fashion_style=self.style, target=doubled_target, weight=2)

        result = fashion_outfit_bonus(self.sheet, doubled_target, self.society)
        self.assertEqual(result, 2 * FASHION_MATCH_BASE)

    def test_worn_facet_not_in_vogue_returns_zero(self) -> None:
        """Case 4: the item's facet is NOT in in_vogue_facets → 0."""
        from world.items.factories import FashionStyleBonusFactory, FashionStyleFactory
        from world.mechanics.factories import ModifierTargetFactory
        from world.societies.factories import SocietyFactory

        # A brand-new style that has NO vogue facets.
        empty_style = FashionStyleFactory(name="EmptyStyle")
        out_target = ModifierTargetFactory(name="OutFacetTarget")
        FashionStyleBonusFactory(fashion_style=empty_style, target=out_target, weight=1)

        out_society = SocietyFactory(name="OutSociety", current_fashion_style=empty_style)

        result = fashion_outfit_bonus(self.sheet, out_target, out_society)
        self.assertEqual(result, 0)

    def test_no_bonus_row_for_target_returns_zero(self) -> None:
        """Case 5: FashionStyleBonus row for queried target doesn't exist → 0."""
        result = fashion_outfit_bonus(self.sheet, self.other_target, self.society)
        self.assertEqual(result, 0)
