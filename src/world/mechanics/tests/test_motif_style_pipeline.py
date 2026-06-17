"""Tests for passive_motif_style_bonuses walker + equipment_walk_total wiring (#1150).

The headline acceptance:
  A character whose Motif binds {Seductive, Sinister} → resonance R, wearing an outfit
  carrying both styles, yields a positive delta in get_modifier_total(sheet, R_target).
  Full combination (both styles worn) beats partial (one style worn).
  A character with no Motif binding, or no matching worn styles, yields delta 0.

Math reference (default config: base_magnitude=5, full_combination_bonus=1.50,
item_mult=1.0, attach_mult=1.0):
  full  (2/2): coverage=1, quality_agg=2*(1*1)=2, bonus=5*1*2*1.5=15 → int=15
  partial(1/2): coverage=0.5, quality_agg=1*(1*1)=1, bonus=5*0.5*1=2.5  → int=2
"""

from __future__ import annotations

from django.test import TestCase


class MotifStylePipelineFullVsPartialTests(TestCase):
    """Headline: full combination (both styles) beats partial (one style)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemStyleFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            TemplateSlotFactory,
        )
        from world.magic.factories import (
            MotifFactory,
            MotifResonanceFactory,
            MotifResonanceStyleFactory,
            ResonanceFactory,
        )
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
        from world.mechanics.services import get_aesthetic_config

        # Ensure the singleton exists with default values.
        cls.config = get_aesthetic_config()

        # Quality tier — unit multipliers (1.0 × 1.0 per style slot).
        cls.quality = QualityTierFactory(name="MotifPipelineCommon", stat_multiplier="1.00")

        # Two styles: Seductive and Sinister.
        from world.items.factories import StyleFactory

        cls.style_seductive = StyleFactory(name="MotifPipelineSeductive")
        cls.style_sinister = StyleFactory(name="MotifPipelineSinister")

        # A different style NOT bound to the motif (for gating tests).
        cls.style_other = StyleFactory(name="MotifPipelineOther")

        # --- Resonance R + ModifierTarget linked to it (category="resonance"). ---
        cls.resonance = ResonanceFactory()
        cls.resonance_category = ModifierCategoryFactory(name="resonance")
        cls.target_r = ModifierTargetFactory(
            name="MotifPipelineTargetR",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
        )

        # A different resonance / target to test cross-resonance gating.
        cls.resonance_other = ResonanceFactory()
        cls.target_other = ModifierTargetFactory(
            name="MotifPipelineTargetOther",
            category=cls.resonance_category,
            target_resonance=cls.resonance_other,
        )

        # --- Character + Sheet + Motif with two style bindings. ---
        cls.char = CharacterFactory(db_key="MotifPipelineChar")
        cls.sheet = CharacterSheetFactory(character=cls.char, primary_persona=False)
        cls.motif = MotifFactory(character=cls.sheet)
        cls.mr = MotifResonanceFactory(motif=cls.motif, resonance=cls.resonance)
        cls.binding_seductive = MotifResonanceStyleFactory(
            motif_resonance=cls.mr, style=cls.style_seductive
        )
        cls.binding_sinister = MotifResonanceStyleFactory(
            motif_resonance=cls.mr, style=cls.style_sinister
        )

        # --- Two items: one tagged Seductive, one tagged Sinister. ---
        cls.template_a = ItemTemplateFactory(name="MotifPipelineItemA")
        TemplateSlotFactory(
            template=cls.template_a,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.item_a = ItemInstanceFactory(template=cls.template_a, quality_tier=cls.quality)
        cls.style_a = ItemStyleFactory(
            item_instance=cls.item_a,
            style=cls.style_seductive,
            attachment_quality_tier=cls.quality,
        )

        cls.template_b = ItemTemplateFactory(name="MotifPipelineItemB")
        TemplateSlotFactory(
            template=cls.template_b,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )
        cls.item_b = ItemInstanceFactory(template=cls.template_b, quality_tier=cls.quality)
        cls.style_b = ItemStyleFactory(
            item_instance=cls.item_b,
            style=cls.style_sinister,
            attachment_quality_tier=cls.quality,
        )

        # Equip BOTH items on cls.char (the full-outfit baseline).
        cls.equipped_a = EquippedItemFactory(
            character=cls.char,
            item_instance=cls.item_a,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.equipped_b = EquippedItemFactory(
            character=cls.char,
            item_instance=cls.item_b,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )

    def _invalidate(self) -> None:
        """Invalidate handler caches so walk re-reads equipped state."""
        self.char.equipped_items.invalidate()

    def test_full_combination_beats_partial(self) -> None:
        """Wearing both bound styles earns more than wearing only one."""
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory
        from world.mechanics.services import get_modifier_total

        # Full outfit (both items equipped in setUpTestData).
        self._invalidate()
        full = get_modifier_total(self.sheet, self.target_r)
        self.assertGreater(full, 0, "Full outfit must yield a positive bonus.")

        # Unequip item_b (Sinister) to produce a partial outfit.
        self.equipped_b.delete()
        self._invalidate()
        try:
            partial = get_modifier_total(self.sheet, self.target_r)
            self.assertGreater(full, partial, "Full combination must beat partial coverage.")
            self.assertGreater(partial, 0, "Partial outfit must still yield a positive bonus.")
        finally:
            # Restore item_b for other tests.
            EquippedItemFactory(
                character=self.char,
                item_instance=self.item_b,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.OUTER,
            )
            self._invalidate()

    def test_full_bonus_exact_value(self) -> None:
        """Full (2/2): int(5 * 1 * 2 * 1.5) == 15."""
        from world.mechanics.services import get_modifier_total

        self._invalidate()
        result = get_modifier_total(self.sheet, self.target_r)
        self.assertEqual(result, 15)

    def test_partial_bonus_exact_value(self) -> None:
        """Partial (1/2): int(5 * 0.5 * 1) == 2."""
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory
        from world.mechanics.services import get_modifier_total

        self.equipped_b.delete()
        self._invalidate()
        try:
            result = get_modifier_total(self.sheet, self.target_r)
            self.assertEqual(result, 2)
        finally:
            EquippedItemFactory(
                character=self.char,
                item_instance=self.item_b,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.OUTER,
            )
            self._invalidate()

    def test_cross_resonance_gating(self) -> None:
        """A binding to resonance R is NOT credited to a target linked to resonance OTHER."""
        from world.mechanics.services import get_modifier_total

        self._invalidate()
        # target_other points at a different resonance; no motif binding there.
        result = get_modifier_total(self.sheet, self.target_other)
        self.assertEqual(result, 0)

    def test_no_worn_styles_yields_zero(self) -> None:
        """When no bound styles are worn, delta is 0."""
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            MotifFactory,
            MotifResonanceFactory,
            MotifResonanceStyleFactory,
        )
        from world.mechanics.services import get_modifier_total

        # Character wearing nothing.
        char2 = CharacterFactory(db_key="MotifPipelineNoWearChar")
        sheet2 = CharacterSheetFactory(character=char2, primary_persona=False)
        motif2 = MotifFactory(character=sheet2)
        mr2 = MotifResonanceFactory(motif=motif2, resonance=self.resonance)
        MotifResonanceStyleFactory(motif_resonance=mr2, style=self.style_seductive)
        MotifResonanceStyleFactory(motif_resonance=mr2, style=self.style_sinister)

        char2.equipped_items.invalidate()
        result = get_modifier_total(sheet2, self.target_r)
        self.assertEqual(result, 0)

    def test_no_motif_yields_zero(self) -> None:
        """A sheet with no Motif (DoesNotExist path) yields 0."""
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.mechanics.services import get_modifier_total

        char3 = CharacterFactory(db_key="MotifPipelineNoMotifChar")
        sheet3 = CharacterSheetFactory(character=char3, primary_persona=False)
        # No Motif created for char3.
        result = get_modifier_total(sheet3, self.target_r)
        self.assertEqual(result, 0)

    def test_motif_no_binding_for_resonance_yields_zero(self) -> None:
        """Motif exists but has no MotifResonance for target_r's resonance → 0."""
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import MotifFactory
        from world.mechanics.services import get_modifier_total

        char4 = CharacterFactory(db_key="MotifPipelineNoBindChar")
        sheet4 = CharacterSheetFactory(character=char4, primary_persona=False)
        MotifFactory(character=sheet4)
        # Motif has no MotifResonance for cls.resonance.
        result = get_modifier_total(sheet4, self.target_r)
        self.assertEqual(result, 0)

    def test_target_without_resonance_link_yields_zero(self) -> None:
        """ModifierTarget with target_resonance=None → gating returns 0."""
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
        from world.mechanics.services import get_modifier_total

        unlinked = ModifierTargetFactory(
            name="MotifPipelineUnlinkedTarget",
            category=ModifierCategoryFactory(name="resonance"),
            target_resonance=None,
        )
        self._invalidate()
        result = get_modifier_total(self.sheet, unlinked)
        self.assertEqual(result, 0)
