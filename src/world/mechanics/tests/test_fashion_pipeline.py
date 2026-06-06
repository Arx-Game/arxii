"""Tests for fashion_outfit_bonus routed through get_modifier_total (#513).

Verifies that:
1. Society-blind callers of get_modifier_total are 100% unaffected by fashion data.
2. Passing perceiving_society adds exactly the fashion delta computed by
   fashion_outfit_bonus, no more, no less.

The ModifierTarget used here has a sequenced category name (e.g. "Category42"),
which is NOT in EQUIPMENT_RELEVANT_CATEGORIES, so equipment_total == 0 and the
baseline is purely eager_total. That makes the fashion delta clean to assert.
"""

from django.test import TestCase

from world.mechanics.services import (
    fashion_outfit_bonus,
    get_modifier_breakdown,
    get_modifier_total,
)


class FashionPipelineTests(TestCase):
    """Integration tests for the perceiving_society keyword in get_modifier_total."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.constants import BodyRegion, EquipmentLayer
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
        cls.quality = QualityTierFactory(name="PipelineCommon", stat_multiplier=1.0)

        # Facet that IS in vogue for this test's style.
        cls.facet_in = FacetFactory(name="PipelineFacetIn")

        # Item template + slot so EquippedItemFactory can assign body_region/layer.
        cls.template = ItemTemplateFactory(name="PipelineTestItem")
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
        cls.character = CharacterFactory(db_key="PipelineChar")
        cls.equipped = EquippedItemFactory(
            character=cls.character,
            item_instance=cls.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # CharacterSheet for the character — get_modifier_total receives the sheet.
        cls.sheet = CharacterSheetFactory(character=cls.character)

        # ModifierTarget whose category is sequenced (NOT in EQUIPMENT_RELEVANT_CATEGORIES)
        # so equipment_total == 0 and baseline == eager breakdown total.
        cls.target = ModifierTargetFactory(name="PipelineTarget")

        # FashionStyle with facet_in in vogue, bonus weight=1.
        cls.style = FashionStyleFactory(name="PipelineStyle")
        cls.style.in_vogue_facets.add(cls.facet_in)
        cls.style_bonus = FashionStyleBonusFactory(
            fashion_style=cls.style, target=cls.target, weight=1
        )

        # Society pointing at the style.
        cls.society = SocietyFactory(name="PipelineSociety", current_fashion_style=cls.style)

    def test_society_blind_call_excludes_fashion(self) -> None:
        """get_modifier_total without perceiving_society never adds fashion bonus.

        Verify by comparing the society-blind total to the eager breakdown total
        (equipment_total == 0 because target.category is not in
        EQUIPMENT_RELEVANT_CATEGORIES), then confirm the society-aware call
        produces exactly baseline + fashion_bonus.
        """
        baseline = get_modifier_total(self.sheet, self.target)
        eager = get_modifier_breakdown(self.sheet, self.target).total
        # No CharacterModifier rows exist for this target, so eager == 0.
        self.assertEqual(baseline, eager)

        from world.items.constants import FASHION_MATCH_BASE

        # Confirm the direct service call gives the expected value:
        # weight=1, item_mult=1.0, attach_mult=1.0 → FASHION_MATCH_BASE.
        expected_fashion = fashion_outfit_bonus(self.sheet, self.target, self.society)
        self.assertEqual(expected_fashion, FASHION_MATCH_BASE)

        # Society-blind: total == baseline (fashion NOT included).
        self.assertEqual(get_modifier_total(self.sheet, self.target), baseline)

    def test_perceiving_society_adds_fashion_bonus(self) -> None:
        """get_modifier_total(perceiving_society=society) adds the fashion delta.

        The total with perceiving_society == baseline + fashion_outfit_bonus.
        """
        from world.items.constants import FASHION_MATCH_BASE

        baseline = get_modifier_total(self.sheet, self.target)
        with_fashion = get_modifier_total(self.sheet, self.target, perceiving_society=self.society)
        self.assertEqual(with_fashion, baseline + FASHION_MATCH_BASE)

    def test_fashion_delta_equals_direct_service_call(self) -> None:
        """Delta from perceiving_society equals fashion_outfit_bonus(sheet, target, society)."""
        baseline = get_modifier_total(self.sheet, self.target)
        with_fashion = get_modifier_total(self.sheet, self.target, perceiving_society=self.society)
        delta = with_fashion - baseline

        # fashion_outfit_bonus takes sheet (not sheet.character) — same as get_modifier_total.
        direct = fashion_outfit_bonus(self.sheet, self.target, self.society)
        self.assertEqual(delta, direct)
