"""End-to-end integration tests for Spec D §5.2 — facet passive bonus pipeline.

Pipeline: build sheet + Thread on Facet + TWO equipped items bearing the Facet +
ThreadPullEffect (tier-0 FLAT_BONUS) → call get_modifier_total(sheet, target) →
assert the sum of per-item contributions is correct.

Math reference:
  contribution per item = int(flat_bonus × item_quality.stat_multiplier
                               × attach_quality.stat_multiplier × max(1, thread.level))
  Setup: flat=5, item_quality=2.00, attach_quality=3.00, level=2
  Per item: int(5 × 2.0 × 3.0 × 2) = 60
  Two items → 120
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase


class FacetPassiveBonusPipelineTests(TestCase):
    """Happy-path: two facet-bearing equipped items sum through get_modifier_total.

    All rows are created in setUpTestData; each test method reads without writing,
    so transaction rollback keeps them isolated.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory

        # 1. Character + CharacterSheet
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import (
            EquippedItemFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            TemplateSlotFactory,
        )
        from world.magic.constants import EffectKind, TargetKind
        from world.magic.factories import (
            FacetFactory,
            ResonanceFactory,
            ThreadFactory,
            ThreadPullEffectFactory,
        )
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        cls.character_obj = CharacterFactory(db_key="FacetPipelineChar")
        cls.sheet = CharacterSheetFactory(character=cls.character_obj, primary_persona=False)

        # 2. Resonance, ModifierCategory("resonance"), ModifierTarget linked to resonance
        cls.resonance = ResonanceFactory()
        cls.resonance_category = ModifierCategoryFactory(name="resonance")
        cls.target = ModifierTargetFactory(
            name="FacetPipelineTarget",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
        )

        # 3. Facet used as thread anchor and item facet
        cls.facet = FacetFactory(name="FacetPipelineFacet")

        # 4. Quality tiers: item_quality stat_multiplier=2.00, attach_quality=3.00
        cls.item_quality = QualityTierFactory(
            name="FacetPipeItemQ", stat_multiplier=Decimal("2.00")
        )
        cls.attach_quality = QualityTierFactory(
            name="FacetPipeAttachQ", stat_multiplier=Decimal("3.00")
        )

        # 5. ItemTemplate with TWO TemplateSlots so both items can be equipped without conflict
        cls.template = ItemTemplateFactory(facet_capacity=2)
        TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )

        # 6. Two ItemInstance + ItemFacet rows, both bearing the same Facet
        cls.instance_a = ItemInstanceFactory(template=cls.template, quality_tier=cls.item_quality)
        cls.item_facet_a = ItemFacetFactory(
            item_instance=cls.instance_a,
            facet=cls.facet,
            attachment_quality_tier=cls.attach_quality,
        )

        cls.instance_b = ItemInstanceFactory(template=cls.template, quality_tier=cls.item_quality)
        cls.item_facet_b = ItemFacetFactory(
            item_instance=cls.instance_b,
            facet=cls.facet,
            attachment_quality_tier=cls.attach_quality,
        )

        # 7. EQUIP both items on distinct slots
        EquippedItemFactory(
            character=cls.character_obj,
            item_instance=cls.instance_a,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        EquippedItemFactory(
            character=cls.character_obj,
            item_instance=cls.instance_b,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )

        # 8. Thread on FACET kind, level=2 → level_factor = max(1, 2) = 2
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.FACET,
            target_facet=cls.facet,
            target_trait=None,
            level=2,
        )

        # 9. Tier-0 FLAT_BONUS ThreadPullEffect for this resonance
        cls.effect = ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

        # 10. Invalidate equipped_items handler cache so it sees the newly equipped rows
        cls.character_obj.equipped_items.invalidate()

    def test_two_facet_items_sum_passive_bonus_through_modifier_total(self) -> None:
        """Two equipped items with Facet → get_modifier_total returns 120.

        Per item: int(5 × 2.00 × 3.00 × max(1, 2)) = int(60.0) = 60.
        Two items → 120.
        """
        from world.mechanics.services import get_modifier_total

        result = get_modifier_total(self.sheet, self.target)
        self.assertEqual(result, 120)


class FacetPassiveBonusNoItemsTests(TestCase):
    """Negative path: no items worn → get_modifier_total returns 0."""

    def test_no_items_worn_returns_zero(self) -> None:
        """Sheet with FACET thread but no equipped items → 0 via get_modifier_total."""
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import TargetKind
        from world.magic.factories import FacetFactory, ResonanceFactory, ThreadFactory
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
        from world.mechanics.services import get_modifier_total

        bare_char = CharacterFactory(db_key="FacetPipelineBareChar")
        bare_sheet = CharacterSheetFactory(character=bare_char, primary_persona=False)
        bare_res = ResonanceFactory()
        bare_facet = FacetFactory(name="FacetPipelineBaredFacet")

        resonance_category = ModifierCategoryFactory(name="resonance")
        bare_target = ModifierTargetFactory(
            name="FacetPipelineBareTarget",
            category=resonance_category,
            target_resonance=bare_res,
        )

        ThreadFactory(
            owner=bare_sheet,
            resonance=bare_res,
            target_kind=TargetKind.FACET,
            target_facet=bare_facet,
            target_trait=None,
            level=2,
        )

        result = get_modifier_total(bare_sheet, bare_target)
        self.assertEqual(result, 0)


class FacetPassiveBonusNoResonanceLinkTests(TestCase):
    """Negative path: ModifierTarget with no target_resonance → 0 via get_modifier_total."""

    def test_target_without_resonance_link_returns_zero(self) -> None:
        """ModifierTarget.target_resonance=None → passive_facet_bonuses gating returns 0."""
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import (
            EquippedItemFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            TemplateSlotFactory,
        )
        from world.magic.constants import EffectKind, TargetKind
        from world.magic.factories import (
            FacetFactory,
            ResonanceFactory,
            ThreadFactory,
            ThreadPullEffectFactory,
        )
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
        from world.mechanics.services import get_modifier_total

        char = CharacterFactory(db_key="FacetPipelineNoLinkChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        resonance = ResonanceFactory()
        facet = FacetFactory(name="FacetPipelineNoLinkFacet")

        # ModifierTarget with NO target_resonance — gating should block passive bonuses
        resonance_category = ModifierCategoryFactory(name="resonance")
        unlinked_target = ModifierTargetFactory(
            name="FacetPipelineUnlinkedTarget",
            category=resonance_category,
            target_resonance=None,
        )

        template = ItemTemplateFactory(facet_capacity=1)
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        instance = ItemInstanceFactory(
            template=template,
            quality_tier=QualityTierFactory(
                name="FacetPipelineNoLinkItemQ", stat_multiplier=Decimal("2.00")
            ),
        )
        ItemFacetFactory(
            item_instance=instance,
            facet=facet,
            attachment_quality_tier=QualityTierFactory(
                name="FacetPipelineNoLinkAttachQ", stat_multiplier=Decimal("3.00")
            ),
        )
        EquippedItemFactory(
            character=char,
            item_instance=instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            target_trait=None,
            level=2,
        )

        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

        char.equipped_items.invalidate()

        result = get_modifier_total(sheet, unlinked_target)
        self.assertEqual(result, 0)
