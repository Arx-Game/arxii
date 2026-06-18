"""Tests for style×facet composition and dilution-only (unbound-style) rules (#1151).

Three behavioral assertions:
  1. Coexistence — an item carrying BOTH an ItemFacet and an ItemStyle contributes
     to passive_facet_bonuses AND passive_motif_style_bonuses independently (both
     non-zero given appropriate bindings).
  2. Dilution-only — a wearer whose MotifResonanceStyle binds resonance R, who ALSO
     wears an item tagged with an unbound style, sees the SAME
     passive_motif_style_bonuses(sheet, target_R) as without the unbound style —
     i.e. the unbound style neither adds nor subtracts.
  3. Partial vs full combination — wearing the full bound style-set yields the
     full_combination_bonus multiplier; a partial set does not.

Math reference (default config: base_magnitude=5, full_combination_bonus=1.50,
item stat_multiplier=1.00, attach stat_multiplier=1.00):
  full  (1/1 bound style): coverage=1, quality_agg=1, bonus=5*1*1*1.5=7.5  → int=7
  partial (0/1 bound style): no bound style worn → 0

For the facet side (flat_bonus=5, item_mult=1.0, attach_mult=1.0, thread level=1):
  passive_facet_bonuses = flat_bonus × item_mult × attach_mult × max(1, level) = 5
"""

from __future__ import annotations

from django.test import TestCase, tag


@tag("postgres")
class StyleFacetCoexistenceTests(TestCase):
    """Coexistence: one item with both ItemFacet and ItemStyle feeds both walkers.

    Tagged postgres because passive_facet_bonuses walks equipped_items via the
    SharedMemoryModel idmap handler; SQLite pk resets cause stale-facet collisions
    across test boundaries (same reason as PassiveFacetBonusesTests in test_services.py).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import (
            EquippedItemFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemStyleFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            StyleFactory,
            TemplateSlotFactory,
        )
        from world.magic.constants import EffectKind, TargetKind
        from world.magic.factories import (
            FacetFactory,
            MotifFactory,
            MotifResonanceFactory,
            MotifResonanceStyleFactory,
            ResonanceFactory,
            ThreadFactory,
            ThreadPullEffectFactory,
        )
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
        from world.mechanics.services import get_aesthetic_config

        cls.config = get_aesthetic_config()

        # Shared quality tier — unit multipliers (1.0 × 1.0).
        cls.quality = QualityTierFactory(name="CoexistCommon", stat_multiplier="1.00")

        # Resonance R + ModifierTarget linked to it.
        cls.resonance = ResonanceFactory()
        cls.resonance_category = ModifierCategoryFactory(name="resonance_coexist")
        cls.target_r = ModifierTargetFactory(
            name="CoexistTargetR",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
        )

        # A style and a facet that will BOTH be attached to the same item instance.
        cls.style = StyleFactory(name="CoexistStyle")
        cls.facet = FacetFactory(name="CoexistFacet")

        # Character + sheet + Motif with a single style binding to resonance R.
        cls.char = CharacterFactory(db_key="CoexistChar")
        cls.sheet = CharacterSheetFactory(character=cls.char, primary_persona=False)
        cls.motif = MotifFactory(character=cls.sheet)
        cls.mr = MotifResonanceFactory(motif=cls.motif, resonance=cls.resonance)
        MotifResonanceStyleFactory(motif_resonance=cls.mr, style=cls.style)

        # FACET thread anchored to cls.facet, resonance=cls.resonance, level=1.
        ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.FACET,
            target_facet=cls.facet,
            target_trait=None,
            level=1,
        )

        # Tier-0 FLAT_BONUS ThreadPullEffect for this resonance (facet walker).
        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

        # One item template + instance equipped on cls.char, carrying BOTH the style
        # and the facet.
        cls.template = ItemTemplateFactory(name="CoexistItem", facet_capacity=1)
        TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.item = ItemInstanceFactory(template=cls.template, quality_tier=cls.quality)
        ItemFacetFactory(
            item_instance=cls.item,
            facet=cls.facet,
            attachment_quality_tier=cls.quality,
        )
        ItemStyleFactory(
            item_instance=cls.item,
            style=cls.style,
            attachment_quality_tier=cls.quality,
        )
        EquippedItemFactory(
            character=cls.char,
            item_instance=cls.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

    def _invalidate(self) -> None:
        self.char.equipped_items.invalidate()

    def test_facet_contribution_is_nonzero(self) -> None:
        """The item's facet feeds passive_facet_bonuses independently.

        flat_bonus=5, item_mult=1.0, attach_mult=1.0, level=1 → 5 * 1 * 1 * 1 = 5.
        """
        from world.mechanics.services import passive_facet_bonuses

        self._invalidate()
        result = passive_facet_bonuses(self.sheet, self.target_r)
        self.assertEqual(result, 5)

    def test_style_contribution_is_nonzero(self) -> None:
        """The item's style feeds passive_motif_style_bonuses independently.

        coverage=1/1, quality_agg=1*(1.0*1.0)=1, bonus=5*1*1*1.5=7.5 → int=7.
        """
        from world.mechanics.services import passive_motif_style_bonuses

        self._invalidate()
        result = passive_motif_style_bonuses(self.sheet, self.target_r)
        self.assertEqual(result, 7)

    def test_both_contributions_present_in_equipment_walk_total(self) -> None:
        """equipment_walk_total includes both the facet bonus and the style bonus."""
        from world.mechanics.services import (
            equipment_walk_total,
            passive_facet_bonuses,
            passive_motif_style_bonuses,
        )

        self._invalidate()
        facet_part = passive_facet_bonuses(self.sheet, self.target_r)
        style_part = passive_motif_style_bonuses(self.sheet, self.target_r)
        total = equipment_walk_total(self.sheet, self.target_r)

        self.assertGreater(facet_part, 0, "Facet contribution must be positive.")
        self.assertGreater(style_part, 0, "Style contribution must be positive.")
        # equipment_walk_total sums facet + style + covenant + mantle contributions;
        # both subcomponents must be present in the total.
        self.assertGreaterEqual(total, facet_part + style_part)


class DilutionOnlyTests(TestCase):
    """Dilution-only: an unbound worn style is inert — no bonus, no penalty.

    The coherence walker iterates only the character's MotifResonanceStyle bindings.
    Any worn ItemStyle outside that bound set is invisible to the walker: it cannot
    inflate (no reinforce) or deflate (no penalty) the bonus.

    SQLite-safe: no passive_facet_bonuses walk — only passive_motif_style_bonuses.
    """

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
        from world.mechanics.services import get_aesthetic_config

        cls.config = get_aesthetic_config()

        cls.quality = QualityTierFactory(name="DilutionCommon", stat_multiplier="1.00")

        # Resonance R + target.
        cls.resonance = ResonanceFactory()
        cls.resonance_category = ModifierCategoryFactory(name="resonance_dilution")
        cls.target_r = ModifierTargetFactory(
            name="DilutionTargetR",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
        )

        # One style that IS bound to resonance R, one style that is NOT.
        cls.style_bound = StyleFactory(name="DilutionBound")
        cls.style_unbound = StyleFactory(name="DilutionUnbound")

        # Character + sheet + Motif binding only style_bound to resonance R.
        cls.char = CharacterFactory(db_key="DilutionChar")
        cls.sheet = CharacterSheetFactory(character=cls.char, primary_persona=False)
        cls.motif = MotifFactory(character=cls.sheet)
        cls.mr = MotifResonanceFactory(motif=cls.motif, resonance=cls.resonance)
        MotifResonanceStyleFactory(motif_resonance=cls.mr, style=cls.style_bound)
        # style_unbound is intentionally NOT bound to any MotifResonance.

        # Item A carries the bound style (TORSO BASE).
        cls.template_a = ItemTemplateFactory(name="DilutionItemA")
        TemplateSlotFactory(
            template=cls.template_a,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.item_a = ItemInstanceFactory(template=cls.template_a, quality_tier=cls.quality)
        ItemStyleFactory(
            item_instance=cls.item_a,
            style=cls.style_bound,
            attachment_quality_tier=cls.quality,
        )

        # Item B carries the unbound style (TORSO OUTER).
        cls.template_b = ItemTemplateFactory(name="DilutionItemB")
        TemplateSlotFactory(
            template=cls.template_b,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )
        cls.item_b = ItemInstanceFactory(template=cls.template_b, quality_tier=cls.quality)
        ItemStyleFactory(
            item_instance=cls.item_b,
            style=cls.style_unbound,
            attachment_quality_tier=cls.quality,
        )

        # Equip item A (bound style) on the character initially.
        cls.equipped_a = EquippedItemFactory(
            character=cls.char,
            item_instance=cls.item_a,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

    def _invalidate(self) -> None:
        self.char.equipped_items.invalidate()

    def test_bound_style_worn_alone_yields_bonus(self) -> None:
        """Wearing only the bound style produces the expected full-coverage bonus.

        coverage=1/1, quality_agg=1, bonus=5*1*1*1.5=7.5 → int=7.
        """
        from world.mechanics.services import passive_motif_style_bonuses

        self._invalidate()
        result = passive_motif_style_bonuses(self.sheet, self.target_r)
        self.assertEqual(result, 7)

    def test_unbound_style_added_does_not_change_bonus(self) -> None:
        """Adding an item with an unbound style leaves the bonus unchanged.

        The unbound style (style_b) is not in the character's MotifResonanceStyle
        bindings for resonance R; the walker ignores it entirely.
        """
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory
        from world.mechanics.services import passive_motif_style_bonuses

        # Baseline: bound style only.
        self._invalidate()
        baseline = passive_motif_style_bonuses(self.sheet, self.target_r)

        # Equip item B (unbound style).
        equipped_b = EquippedItemFactory(
            character=self.char,
            item_instance=self.item_b,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )
        self._invalidate()
        try:
            with_unbound = passive_motif_style_bonuses(self.sheet, self.target_r)
            self.assertEqual(
                with_unbound,
                baseline,
                "Wearing an unbound style must not change the coherence bonus "
                f"(expected {baseline}, got {with_unbound}).",
            )
        finally:
            equipped_b.delete()
            self._invalidate()

    def test_unbound_style_alone_yields_zero(self) -> None:
        """A character wearing only an unbound style (no bound style worn) gets 0.

        The bound style is unequipped; only the unbound style remains. Since no
        bound style is worn, coverage=0 → bonus=0 regardless of unbound style.
        """
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory
        from world.mechanics.services import passive_motif_style_bonuses

        # Unequip item A (the bound style).
        self.equipped_a.delete()
        self._invalidate()
        try:
            # Equip item B (the unbound style only).
            equipped_b = EquippedItemFactory(
                character=self.char,
                item_instance=self.item_b,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.OUTER,
            )
            self._invalidate()
            try:
                result = passive_motif_style_bonuses(self.sheet, self.target_r)
                self.assertEqual(
                    result,
                    0,
                    "Wearing only an unbound style must produce zero bonus.",
                )
            finally:
                equipped_b.delete()
                self._invalidate()
        finally:
            # Restore item A for subsequent tests.
            from world.items.constants import BodyRegion, EquipmentLayer

            EquippedItemFactory(
                character=self.char,
                item_instance=self.item_a,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.BASE,
            )
            self._invalidate()


class PartialVsFullCombinationTests(TestCase):
    """Partial vs full combination bonus scaling (single-resonance axis).

    Re-asserts the core invariant at the composition-test level, independent of
    test_motif_style_pipeline.py: full coverage yields the full_combination_bonus
    multiplier; partial coverage does not.

    SQLite-safe: no passive_facet_bonuses walk.

    Math (default config: base_magnitude=5, full_combination_bonus=1.50,
    item_mult=1.0, attach_mult=1.0):
      full  (2/2): coverage=1, quality_agg=2, bonus=5*1*2*1.5=15 → int=15
      partial(1/2): coverage=0.5, quality_agg=1, bonus=5*0.5*1=2.5 → int=2
    """

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
        from world.mechanics.services import get_aesthetic_config

        cls.config = get_aesthetic_config()
        cls.quality = QualityTierFactory(name="ComboCommon", stat_multiplier="1.00")

        cls.resonance = ResonanceFactory()
        cls.resonance_category = ModifierCategoryFactory(name="resonance_combo")
        cls.target_r = ModifierTargetFactory(
            name="ComboTargetR",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
        )

        cls.style_a = StyleFactory(name="ComboStyleA")
        cls.style_b = StyleFactory(name="ComboStyleB")

        cls.char = CharacterFactory(db_key="ComboChar")
        cls.sheet = CharacterSheetFactory(character=cls.char, primary_persona=False)
        cls.motif = MotifFactory(character=cls.sheet)
        cls.mr = MotifResonanceFactory(motif=cls.motif, resonance=cls.resonance)
        MotifResonanceStyleFactory(motif_resonance=cls.mr, style=cls.style_a)
        MotifResonanceStyleFactory(motif_resonance=cls.mr, style=cls.style_b)

        # Item carrying style_a (TORSO BASE).
        cls.template_a = ItemTemplateFactory(name="ComboItemA")
        TemplateSlotFactory(
            template=cls.template_a,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.item_a = ItemInstanceFactory(template=cls.template_a, quality_tier=cls.quality)
        ItemStyleFactory(
            item_instance=cls.item_a,
            style=cls.style_a,
            attachment_quality_tier=cls.quality,
        )

        # Item carrying style_b (TORSO OUTER).
        cls.template_b = ItemTemplateFactory(name="ComboItemB")
        TemplateSlotFactory(
            template=cls.template_b,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )
        cls.item_b = ItemInstanceFactory(template=cls.template_b, quality_tier=cls.quality)
        ItemStyleFactory(
            item_instance=cls.item_b,
            style=cls.style_b,
            attachment_quality_tier=cls.quality,
        )

        # Equip both items on cls.char (full-outfit baseline).
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
        self.char.equipped_items.invalidate()

    def test_full_combination_bonus_applied(self) -> None:
        """Full coverage (2/2) applies the full_combination_bonus multiplier.

        Expected: int(5 * 1.0 * 2 * 1.5) = 15.
        """
        from world.mechanics.services import passive_motif_style_bonuses

        self._invalidate()
        result = passive_motif_style_bonuses(self.sheet, self.target_r)
        self.assertEqual(result, 15)

    def test_partial_combination_no_multiplier(self) -> None:
        """Partial coverage (1/2) does NOT apply the full_combination_bonus.

        Expected: int(5 * 0.5 * 1) = 2.
        """
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory
        from world.mechanics.services import passive_motif_style_bonuses

        self.equipped_b.delete()
        self._invalidate()
        try:
            result = passive_motif_style_bonuses(self.sheet, self.target_r)
            self.assertEqual(result, 2)
        finally:
            EquippedItemFactory(
                character=self.char,
                item_instance=self.item_b,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.OUTER,
            )
            self._invalidate()

    def test_full_beats_partial(self) -> None:
        """Full combination bonus is strictly greater than partial coverage bonus."""
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory
        from world.mechanics.services import passive_motif_style_bonuses

        self._invalidate()
        full = passive_motif_style_bonuses(self.sheet, self.target_r)

        self.equipped_b.delete()
        self._invalidate()
        try:
            partial = passive_motif_style_bonuses(self.sheet, self.target_r)
            self.assertGreater(full, partial)
            self.assertGreater(partial, 0)
        finally:
            EquippedItemFactory(
                character=self.char,
                item_instance=self.item_b,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.OUTER,
            )
            self._invalidate()
