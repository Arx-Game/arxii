"""Coherence bonus scales with the worn style's audacity tier (#2029).

Two otherwise-identical setups (same base_magnitude, unit item/attach quality
multipliers, single bound style worn — full combination) differing only in the
bound style's ``audacity`` must produce different ``motif_coherence_bonus``
results, ranked UNDERSTATED < EXPRESSIVE < BOLD < OUTRAGEOUS.

Math reference (default config: base_magnitude=5, full_combination_bonus=1.50,
item stat_multiplier=1.00, attach stat_multiplier=1.00; coverage=1/1 → full combo
applies):
  UNDERSTATED (x0.75): bonus = 5 * 1 * (1*0.75) * 1.5 = 5.625 → int = 5
  EXPRESSIVE  (x1.00, default): bonus = 5 * 1 * (1*1.00) * 1.5 = 7.5   → int = 7
  BOLD        (x1.35): bonus = 5 * 1 * (1*1.35) * 1.5 = 10.125 → int = 10

SQLite-safe: no passive_facet_bonuses walk (mirrors PartialVsFullCombinationTests
in test_aesthetic_composition.py).
"""

from __future__ import annotations

from django.test import TestCase

from world.items.constants import StyleAudacity


def _build_worn_style_scenario(*, audacity: int, name_prefix: str):
    """Build a character wearing one item carrying one Style at ``audacity``,
    bound (via Motif) to a fresh Resonance. Returns (sheet, target_r).
    """
    from evennia_extensions.factories import CharacterFactory
    from world.character_sheets.factories import CharacterSheetFactory
    from world.items.constants import BodyRegion, EquipmentLayer
    from world.items.factories import (
        EquippedItemFactory,
        ItemInstanceFactory,
        ItemStyleFactory,
        ItemTemplateFactory,
        QualityTierFactory,
        StyleFactory,
        TemplateSlotFactory,
    )
    from world.magic.factories import (
        MotifFactory,
        MotifResonanceFactory,
        MotifResonanceStyleFactory,
        ResonanceFactory,
    )
    from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

    quality = QualityTierFactory(name=f"{name_prefix}Common", stat_multiplier="1.00")
    resonance = ResonanceFactory()
    resonance_category = ModifierCategoryFactory(name=f"resonance_{name_prefix.lower()}")
    target_r = ModifierTargetFactory(
        name=f"{name_prefix}TargetR",
        category=resonance_category,
        target_resonance=resonance,
    )

    style = StyleFactory(name=f"{name_prefix}Style", audacity=audacity)

    char = CharacterFactory(db_key=f"{name_prefix}Char")
    sheet = CharacterSheetFactory(character=char, primary_persona=False)
    motif = MotifFactory(character=sheet)
    mr = MotifResonanceFactory(motif=motif, resonance=resonance)
    MotifResonanceStyleFactory(motif_resonance=mr, style=style)

    template = ItemTemplateFactory(name=f"{name_prefix}Item")
    TemplateSlotFactory(
        template=template,
        body_region=BodyRegion.TORSO,
        equipment_layer=EquipmentLayer.BASE,
    )
    item = ItemInstanceFactory(template=template, quality_tier=quality)
    ItemStyleFactory(item_instance=item, style=style, attachment_quality_tier=quality)
    EquippedItemFactory(
        character=char,
        item_instance=item,
        body_region=BodyRegion.TORSO,
        equipment_layer=EquipmentLayer.BASE,
    )
    char.equipped_items.invalidate()
    return sheet, target_r


class AudacityCoherenceScalingTests(TestCase):
    """Identical worn setups differing only in style audacity yield different bonuses."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.mechanics.services import get_aesthetic_config

        cls.config = get_aesthetic_config()
        cls.understated_sheet, cls.understated_target = _build_worn_style_scenario(
            audacity=StyleAudacity.UNDERSTATED, name_prefix="Understated"
        )
        cls.expressive_sheet, cls.expressive_target = _build_worn_style_scenario(
            audacity=StyleAudacity.EXPRESSIVE, name_prefix="Expressive"
        )
        cls.bold_sheet, cls.bold_target = _build_worn_style_scenario(
            audacity=StyleAudacity.BOLD, name_prefix="Bold"
        )
        cls.outrageous_sheet, cls.outrageous_target = _build_worn_style_scenario(
            audacity=StyleAudacity.OUTRAGEOUS, name_prefix="Outrageous"
        )

    def test_bonus_ascends_with_audacity_tier(self) -> None:
        from world.mechanics.services import passive_motif_style_bonuses

        understated = passive_motif_style_bonuses(self.understated_sheet, self.understated_target)
        expressive = passive_motif_style_bonuses(self.expressive_sheet, self.expressive_target)
        bold = passive_motif_style_bonuses(self.bold_sheet, self.bold_target)
        outrageous = passive_motif_style_bonuses(self.outrageous_sheet, self.outrageous_target)

        self.assertEqual(understated, 5)
        self.assertEqual(expressive, 7)
        self.assertEqual(bold, 10)
        self.assertLess(understated, expressive)
        self.assertLess(expressive, bold)
        self.assertLess(bold, outrageous)

    def test_identical_items_differing_only_in_audacity_diverge(self) -> None:
        """The UNDERSTATED and BOLD setups are otherwise identical (same item/attach
        quality multipliers, same coverage) — only the bound style's audacity differs.
        """
        from world.mechanics.services import passive_motif_style_bonuses

        understated = passive_motif_style_bonuses(self.understated_sheet, self.understated_target)
        bold = passive_motif_style_bonuses(self.bold_sheet, self.bold_target)
        self.assertNotEqual(understated, bold)
