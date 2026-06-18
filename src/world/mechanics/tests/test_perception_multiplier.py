"""Tests for perception-breadth amplification on the coherence walker (#1152).

A character whose style-presentation has been endorsed by N distinct peers
receives a bonus on ``passive_motif_style_bonuses`` that scales from
factor=1.0 (0 endorsers) up to factor=perception_multiplier (N>=cap).

Math reference (default config: base_magnitude=5, full_combination_bonus=1.50,
perception_multiplier=2.00, perception_breadth_cap=5, stat_multiplier=1.00):
  baseline (0 endorsers, 1/1 style):
    coverage=1, quality_agg=1, bonus=5*1*1*1.5=7.5 → int(7.5)=7
  partial endorsers (n=2, cap=5):
    factor = 1 + (2.00-1) * (2/5) = 1 + 0.40 = 1.40
    bonus = 7.5 * 1.40 = 10.5 → int(10)=10
  saturated (n=5 or n=6, cap=5):
    factor = 1 + (2.00-1) * (5/5) = 2.00
    bonus = 7.5 * 2.00 = 15.0 → int(15)=15
"""

from __future__ import annotations

from django.test import TestCase


class PerceptionMultiplierTests(TestCase):
    """Perception-breadth amplification on the coherence walker.

    Uses SQLite; no cross-app SharedMemoryModel idmap hazards because
    we only walk the motif-style path (no facet / thread walkers).
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

        # Singleton config — set perception_multiplier=2.00, cap=5.
        config = get_aesthetic_config()
        from decimal import Decimal

        config.perception_multiplier = Decimal("2.00")
        config.perception_breadth_cap = 5
        config.save()
        cls.config = config

        # Quality tier with unit multipliers (1.0 × 1.0).
        cls.quality = QualityTierFactory(name="PerceptionMultCommon", stat_multiplier="1.00")

        # One bound style.
        cls.style = StyleFactory(name="PerceptionMultStyle")

        # Resonance R + ModifierTarget linked to it.
        cls.resonance = ResonanceFactory()
        cls.resonance_category = ModifierCategoryFactory(name="resonance_perception")
        cls.target_r = ModifierTargetFactory(
            name="PerceptionMultTargetR",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
        )

        # Wearer character + sheet + Motif with one style binding.
        cls.char = CharacterFactory(db_key="PerceptionMultChar")
        cls.sheet = CharacterSheetFactory(character=cls.char, primary_persona=False)
        cls.motif = MotifFactory(character=cls.sheet)
        cls.mr = MotifResonanceFactory(motif=cls.motif, resonance=cls.resonance)
        MotifResonanceStyleFactory(motif_resonance=cls.mr, style=cls.style)

        # One item carrying cls.style, equipped on cls.char.
        cls.template = ItemTemplateFactory(name="PerceptionMultItem")
        TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.item = ItemInstanceFactory(template=cls.template, quality_tier=cls.quality)
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

        # Endorser sheets (distinct characters) — created once, reused across tests.
        cls.endorsers = [
            CharacterSheetFactory(
                character=CharacterFactory(db_key=f"PerceptionEndorser{i}"),
                primary_persona=False,
            )
            for i in range(6)  # 6 endorsers: covers partial (2) and over-cap (5, 6) cases
        ]

    def setUp(self) -> None:
        """Flush idmapper cache so each test re-reads equipped_items cleanly."""
        self.char.equipped_items.invalidate()

    def _baseline(self) -> int:
        """Bonus with zero endorsers (factor must be 1)."""
        from world.mechanics.services import passive_motif_style_bonuses

        return passive_motif_style_bonuses(self.sheet, self.target_r)

    def test_zero_endorsers_equals_baseline(self) -> None:
        """0 endorsers → factor=1; bonus unchanged from plain coherence walk."""
        # With 0 StylePresentationEndorsements for cls.sheet + cls.resonance,
        # factor = 1 + (2.00-1) * (0/5) = 1.00.
        # Baseline = int(5 * 1 * 1 * 1.5) = int(7.5) = 7.
        from world.mechanics.services import passive_motif_style_bonuses

        result = passive_motif_style_bonuses(self.sheet, self.target_r)
        self.assertEqual(result, 7)

    def test_partial_endorsers_between_baseline_and_saturated(self) -> None:
        """2 distinct endorsers (< cap=5) → bonus strictly between baseline and saturated."""
        from world.magic.factories import StylePresentationEndorsementFactory
        from world.mechanics.services import passive_motif_style_bonuses
        from world.scenes.factories import SceneFactory

        scene = SceneFactory()
        StylePresentationEndorsementFactory(
            endorser_sheet=self.endorsers[0],
            endorsee_sheet=self.sheet,
            scene=scene,
            resonance=self.resonance,
        )
        StylePresentationEndorsementFactory(
            endorser_sheet=self.endorsers[1],
            endorsee_sheet=self.sheet,
            scene=scene,
            resonance=self.resonance,
        )

        result = passive_motif_style_bonuses(self.sheet, self.target_r)
        baseline = 7
        saturated = 15  # int(7.5 * 2.00) = int(15.0) = 15
        self.assertGreater(result, baseline, "2 endorsers must beat baseline.")
        self.assertLess(result, saturated, "2 endorsers must not saturate.")
        # Exact: factor = 1 + 1*(2/5) = 1.40; 7.5*1.40=10.5 → int=10
        self.assertEqual(result, 10)

    def test_at_cap_endorsers_saturates(self) -> None:
        """N == cap (5) → factor=perception_multiplier=2.00 → saturated bonus."""
        from world.magic.factories import StylePresentationEndorsementFactory
        from world.mechanics.services import passive_motif_style_bonuses
        from world.scenes.factories import SceneFactory

        scene = SceneFactory()
        for i in range(5):
            StylePresentationEndorsementFactory(
                endorser_sheet=self.endorsers[i],
                endorsee_sheet=self.sheet,
                scene=scene,
                resonance=self.resonance,
            )

        result = passive_motif_style_bonuses(self.sheet, self.target_r)
        # int(7.5 * 2.00) = 15
        self.assertEqual(result, 15)

    def test_over_cap_endorsers_same_as_at_cap(self) -> None:
        """N > cap (6 endorsers, cap=5) → same bonus as N==cap (capped)."""
        from world.magic.factories import StylePresentationEndorsementFactory
        from world.mechanics.services import passive_motif_style_bonuses
        from world.scenes.factories import SceneFactory

        # Use different scenes to avoid unique-constraint on (endorser, endorsee, scene).
        scene1 = SceneFactory()
        scene2 = SceneFactory()
        for i in range(5):
            StylePresentationEndorsementFactory(
                endorser_sheet=self.endorsers[i],
                endorsee_sheet=self.sheet,
                scene=scene1,
                resonance=self.resonance,
            )
        # 6th endorser in a different scene — still a distinct endorser_sheet.
        StylePresentationEndorsementFactory(
            endorser_sheet=self.endorsers[5],
            endorsee_sheet=self.sheet,
            scene=scene2,
            resonance=self.resonance,
        )

        result = passive_motif_style_bonuses(self.sheet, self.target_r)
        self.assertEqual(result, 15)

    def test_duplicate_endorser_scene_counts_once(self) -> None:
        """Same endorser in two scenes → still counts as 1 distinct endorser."""
        from world.magic.factories import StylePresentationEndorsementFactory
        from world.mechanics.services import passive_motif_style_bonuses
        from world.scenes.factories import SceneFactory

        scene_a = SceneFactory()
        scene_b = SceneFactory()
        endorser = self.endorsers[0]
        StylePresentationEndorsementFactory(
            endorser_sheet=endorser,
            endorsee_sheet=self.sheet,
            scene=scene_a,
            resonance=self.resonance,
        )
        StylePresentationEndorsementFactory(
            endorser_sheet=endorser,
            endorsee_sheet=self.sheet,
            scene=scene_b,
            resonance=self.resonance,
        )

        # 1 distinct endorser, cap=5: factor = 1 + 1*(1/5) = 1.20; 7.5*1.20=9.0 → int=9
        result = passive_motif_style_bonuses(self.sheet, self.target_r)
        self.assertEqual(result, 9)

    def test_wrong_resonance_endorsement_not_counted(self) -> None:
        """Endorsements for a different resonance do not amplify this resonance's bonus."""
        from world.magic.factories import ResonanceFactory, StylePresentationEndorsementFactory
        from world.mechanics.services import passive_motif_style_bonuses
        from world.scenes.factories import SceneFactory

        other_resonance = ResonanceFactory()
        scene = SceneFactory()
        # Add 5 endorsements for a different resonance — should not affect target_r walk.
        for i in range(5):
            StylePresentationEndorsementFactory(
                endorser_sheet=self.endorsers[i],
                endorsee_sheet=self.sheet,
                scene=scene,
                resonance=other_resonance,
            )

        result = passive_motif_style_bonuses(self.sheet, self.target_r)
        # Factor stays 1 (no endorsements for cls.resonance).
        self.assertEqual(result, 7)
