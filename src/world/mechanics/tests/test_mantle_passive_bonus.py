"""Integration tests for Spec D §5.2 — passive mantle bonus pipeline (#512).

Pipeline: build sheet + MANTLE-kind Thread anchored to a Mantle +
ThreadPullEffect (tier-0 FLAT_BONUS, target_kind=MANTLE) → call
get_modifier_total(sheet, target) → assert the contribution equals
flat_bonus_amount × max(1, thread.level) with NO item/attachment quality scaling.

Math reference:
  contribution = flat_bonus × max(1, thread.level)
  Setup: flat=5, level=3 → 5 × 3 = 15 (independent of any equipped item quality)
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase


class MantlePassiveBonusPipelineTests(TestCase):
    """Happy path: a MANTLE thread contributes flat × level through get_modifier_total.

    Rows are created in setUpTestData; each test reads without writing, so
    transaction rollback keeps them isolated.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import MantleFactory
        from world.magic.constants import EffectKind, TargetKind
        from world.magic.factories import (
            ResonanceFactory,
            ThreadFactory,
            ThreadPullEffectFactory,
        )
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        cls.flat = 5
        cls.level = 3

        # 1. Character + CharacterSheet
        cls.character_obj = CharacterFactory(db_key="MantlePipelineChar")
        cls.sheet = CharacterSheetFactory(character=cls.character_obj, primary_persona=False)

        # 2. Resonance + ModifierTarget linked to it via target_resonance
        cls.resonance = ResonanceFactory()
        cls.resonance_category = ModifierCategoryFactory(name="resonance")
        cls.target = ModifierTargetFactory(
            name="MantlePipelineTarget",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
        )

        # 3. A Mantle to anchor the thread on
        cls.mantle = MantleFactory(name="MantlePipelineMantle")

        # 4. MANTLE-kind Thread (level=3). ThreadFactory defaults to TRAIT; build
        #    the MANTLE discriminator + typed FK directly (clearing target_trait)
        #    instead of create-then-update — Thread is a SharedMemoryModel, so a
        #    QuerySet.update() writes the DB but leaves the idmapper-cached row
        #    stale (the create-then-update read returns the old TRAIT shape).
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            level=cls.level,
            target_kind=TargetKind.MANTLE,
            target_mantle=cls.mantle,
            target_trait=None,
        )

        # 5. Tier-0 FLAT_BONUS ThreadPullEffect for this resonance (MANTLE kind)
        cls.effect = ThreadPullEffectFactory(
            target_kind=TargetKind.MANTLE,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=cls.flat,
        )

    def test_mantle_thread_contributes_flat_times_level(self) -> None:
        """MANTLE thread (level 3) + FLAT_BONUS 5 → get_modifier_total includes 15."""
        from world.mechanics.services import get_modifier_total

        # Handler caches live on the (idmapper-shared) Character instance and leak
        # across test methods; invalidate so the walk re-reads setUpTestData rows.
        self.character_obj.threads.invalidate()
        self.character_obj.equipped_items.invalidate()

        result = get_modifier_total(self.sheet, self.target)
        self.assertEqual(result, self.flat * self.level)

    def test_contribution_ignores_equipped_item_quality(self) -> None:
        """Equipping high-quality items must NOT scale the mantle contribution.

        The mantle bonus comes from the thread itself, not from any joined item,
        so the total stays flat × level regardless of worn-item quality.
        """
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            TemplateSlotFactory,
        )
        from world.mechanics.services import get_modifier_total

        template = ItemTemplateFactory(facet_capacity=1)
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        instance = ItemInstanceFactory(
            template=template,
            quality_tier=QualityTierFactory(
                name="MantlePipelineHighQ", stat_multiplier=Decimal("9.00")
            ),
        )
        EquippedItemFactory(
            character=self.character_obj,
            item_instance=instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        # Handler caches leak across methods on the idmapper-shared Character;
        # invalidate so threads + the freshly equipped item are both seen.
        self.character_obj.threads.invalidate()
        self.character_obj.equipped_items.invalidate()

        result = get_modifier_total(self.sheet, self.target)
        self.assertEqual(result, self.flat * self.level)


class MantlePassiveBonusNoThreadTests(TestCase):
    """Negative path: no MANTLE thread → 0 via get_modifier_total."""

    def test_no_mantle_thread_returns_zero(self) -> None:
        """A sheet with no MANTLE thread gets no mantle contribution."""
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import EffectKind, TargetKind
        from world.magic.factories import ResonanceFactory, ThreadPullEffectFactory
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
        from world.mechanics.services import get_modifier_total

        char = CharacterFactory(db_key="MantlePipelineNoThreadChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        resonance = ResonanceFactory()

        resonance_category = ModifierCategoryFactory(name="resonance")
        target = ModifierTargetFactory(
            name="MantlePipelineNoThreadTarget",
            category=resonance_category,
            target_resonance=resonance,
        )

        # Authored effect exists, but the character owns no MANTLE thread.
        ThreadPullEffectFactory(
            target_kind=TargetKind.MANTLE,
            resonance=resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

        result = get_modifier_total(sheet, target)
        self.assertEqual(result, 0)


class MantlePassiveBonusNoResonanceLinkTests(TestCase):
    """Negative path: ModifierTarget with no target_resonance → 0 (gate)."""

    def test_target_without_resonance_link_returns_zero(self) -> None:
        """ModifierTarget.target_resonance=None → mantle gating returns 0."""
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import MantleFactory
        from world.magic.constants import EffectKind, TargetKind
        from world.magic.factories import (
            ResonanceFactory,
            ThreadFactory,
            ThreadPullEffectFactory,
        )
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
        from world.mechanics.services import get_modifier_total

        char = CharacterFactory(db_key="MantlePipelineNoLinkChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        resonance = ResonanceFactory()
        mantle = MantleFactory(name="MantlePipelineNoLinkMantle")

        # ModifierTarget with NO target_resonance — gating should block bonuses.
        resonance_category = ModifierCategoryFactory(name="resonance")
        unlinked_target = ModifierTargetFactory(
            name="MantlePipelineUnlinkedTarget",
            category=resonance_category,
            target_resonance=None,
        )

        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            level=3,
            target_kind=TargetKind.MANTLE,
            target_mantle=mantle,
            target_trait=None,
        )

        ThreadPullEffectFactory(
            target_kind=TargetKind.MANTLE,
            resonance=resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

        result = get_modifier_total(sheet, unlinked_target)
        self.assertEqual(result, 0)
