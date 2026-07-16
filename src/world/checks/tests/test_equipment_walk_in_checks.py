"""Spec D §5.5 — equipment walk + fashion surface in collect_check_modifiers (#512).

These tests prove that the facet + covenant-role + mantle passive bonuses (the
"equipment walk") AND the perception-relative fashion bonus surface through the
central check seam ``collect_check_modifiers`` — not just through
``get_modifier_total`` (which combat never calls).

Setup uses a single ModifierTarget that is simultaneously:
  * ``category.name == "resonance"`` → in EQUIPMENT_RELEVANT_CATEGORIES, so the
    equipment walk runs;
  * linked to a Resonance via ``target_resonance`` → the facet/mantle passive
    walks gate true;
  * the reverse ``modifier_target`` of a CheckType via ``target_check_type`` →
    ``collect_check_modifiers`` resolves it as the scoped target.

Known-integer math (asserted exactly, to prove the eager CharacterModifier total
is counted exactly once — never double-counted by the equipment block):
  * eager CharacterModifier value         = 11
  * facet:  flat 5 × item 2.0 × attach 3.0 × level 2 = 60
  * mantle: flat 7 × level 3                          = 21
  * fashion: FASHION_MATCH_BASE 1 × item 1.0 × attach 1.0 × weight 2 = 2
  → CHARACTER (eager) 11 + EQUIPMENT walk (60 + 21 = 81) + FASHION 2 = 94
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.checks.constants import ModifierSourceKind


class EquipmentWalkInChecksTests(TestCase):
    """Facet + mantle + fashion + eager all surface through collect_check_modifiers."""

    @classmethod
    def setUpTestData(cls) -> None:  # noqa: PLR0915 - end-to-end fixture spans many rows
        from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
        from world.areas.constants import AreaLevel
        from world.areas.factories import AreaFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.checks.factories import CheckTypeFactory
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import (
            EquippedItemFactory,
            FashionStyleBonusFactory,
            FashionStyleFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            MantleFactory,
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
        from world.mechanics.factories import (
            CharacterModifierFactory,
            DistinctionModifierSourceFactory,
            ModifierCategoryFactory,
            ModifierTargetFactory,
        )
        from world.realms.models import Realm
        from world.scenes.factories import SceneFactory
        from world.societies.factories import SocietyFactory

        cls.eager_value = 11
        cls.expected_facet = 60
        cls.expected_mantle = 21
        cls.expected_fashion = 2
        cls.expected_walk = cls.expected_facet + cls.expected_mantle  # 81
        cls.expected_total = cls.eager_value + cls.expected_walk + cls.expected_fashion  # 94

        # --- Character + sheet ---
        cls.character_obj = CharacterFactory(db_key="EquipWalkChecksChar")
        cls.sheet = CharacterSheetFactory(character=cls.character_obj, primary_persona=False)

        # --- Resonance shared by both the facet thread and the mantle thread ---
        cls.resonance = ResonanceFactory()

        # --- CheckType + scoped ModifierTarget (resonance category, linked 3 ways) ---
        cls.check_type = CheckTypeFactory(name="EquipWalkCombatCheck")
        cls.resonance_category = ModifierCategoryFactory(name="resonance")
        cls.target = ModifierTargetFactory(
            name="equip_walk_target",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
            target_check_type=cls.check_type,
        )

        # --- Eager CharacterModifier on the scoped target (the CHARACTER row) ---
        source = DistinctionModifierSourceFactory(distinction_effect__target=cls.target)
        cls.eager_modifier = CharacterModifierFactory(
            character=cls.sheet, value=cls.eager_value, source=source, target=cls.target
        )

        # --- FACET walk: thread + equipped item bearing the facet ---
        cls.facet = FacetFactory(name="EquipWalkChecksFacet")
        cls.item_quality = QualityTierFactory(
            name="EquipWalkItemQ", stat_multiplier=Decimal("2.00")
        )
        cls.attach_quality = QualityTierFactory(
            name="EquipWalkAttachQ", stat_multiplier=Decimal("3.00")
        )
        cls.template = ItemTemplateFactory(name="EquipWalkFacetItem", facet_capacity=1)
        TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.facet_item = ItemInstanceFactory(template=cls.template, quality_tier=cls.item_quality)
        cls.item_facet = ItemFacetFactory(
            item_instance=cls.facet_item,
            facet=cls.facet,
            attachment_quality_tier=cls.attach_quality,
        )
        EquippedItemFactory(
            character=cls.character_obj,
            item_instance=cls.facet_item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        # FACET thread (level 2). Build the discriminator + typed FK directly —
        # NEVER create-then-update (Thread is a SharedMemoryModel; update() leaves
        # the idmapper-cached instance stale and invisible to the walk).
        cls.facet_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            level=2,
            target_kind=TargetKind.FACET,
            target_facet=cls.facet,
            target_trait=None,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )

        # --- MANTLE walk: thread + authored mantle ThreadPullEffect ---
        cls.mantle = MantleFactory(name="EquipWalkChecksMantle")
        cls.mantle_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            level=3,
            target_kind=TargetKind.MANTLE,
            target_mantle=cls.mantle,
            target_trait=None,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.MANTLE,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=7,
        )

        # --- FASHION: scene → location → area → realm → society → style ---
        cls.fashion_facet = FacetFactory(name="EquipWalkChecksFashionFacet")
        cls.unit_quality = QualityTierFactory(
            name="EquipWalkUnitQ", stat_multiplier=Decimal("1.00")
        )
        cls.fashion_template = ItemTemplateFactory(name="EquipWalkFashionItem", facet_capacity=1)
        TemplateSlotFactory(
            template=cls.fashion_template,
            body_region=BodyRegion.HEAD,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.fashion_item = ItemInstanceFactory(
            template=cls.fashion_template, quality_tier=cls.unit_quality
        )
        cls.fashion_item_facet = ItemFacetFactory(
            item_instance=cls.fashion_item,
            facet=cls.fashion_facet,
            attachment_quality_tier=cls.unit_quality,
        )
        EquippedItemFactory(
            character=cls.character_obj,
            item_instance=cls.fashion_item,
            body_region=BodyRegion.HEAD,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.style = FashionStyleFactory(name="EquipWalkChecksStyle")
        cls.style.in_vogue_facets.add(cls.fashion_facet)
        FashionStyleBonusFactory(fashion_style=cls.style, target=cls.target, weight=2)

        cls.realm = Realm.objects.create(name="EquipWalkChecksRealm")
        cls.society = SocietyFactory(
            name="EquipWalkChecksSociety",
            realm=cls.realm,
            current_fashion_style=cls.style,
        )
        cls.area = AreaFactory(
            name="EquipWalkChecksArea",
            level=AreaLevel.WARD,
            realm=cls.realm,
            dominant_society=cls.society,
        )
        cls.room_obj = ObjectDBFactory(
            db_key="EquipWalkChecksRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        from evennia_extensions.models import RoomProfile

        RoomProfile.objects.update_or_create(objectdb=cls.room_obj, defaults={"area": cls.area})
        cls.scene = SceneFactory(location=cls.room_obj)

    def setUp(self) -> None:
        # Handler caches live on the idmapper-shared Character and leak across
        # test methods; invalidate so the walk re-reads setUpTestData rows.
        self.character_obj.threads.invalidate()
        self.character_obj.equipped_items.invalidate()

    def _contribs(self, breakdown, kind):
        return [c for c in breakdown.contributions if c.source_kind == kind]

    def test_walk_and_fashion_surface_with_exact_total(self) -> None:
        """In a scene: eager + facet + mantle + fashion, eager counted once."""
        from world.checks.services import collect_check_modifiers

        breakdown = collect_check_modifiers(self.sheet, self.check_type, scene=self.scene)

        # Exact total proves NO double-count of the eager CharacterModifier total.
        self.assertEqual(breakdown.total, self.expected_total)

        character_contribs = self._contribs(breakdown, ModifierSourceKind.CHARACTER)
        self.assertEqual(len(character_contribs), 1)
        self.assertEqual(character_contribs[0].value, self.eager_value)

        equipment_contribs = self._contribs(breakdown, ModifierSourceKind.EQUIPMENT)
        labels = {c.source_label: c.value for c in equipment_contribs}
        self.assertEqual(labels.get("Equipment & attunement"), self.expected_walk)

        fashion_contribs = self._contribs(breakdown, ModifierSourceKind.FASHION)
        self.assertEqual(len(fashion_contribs), 1)
        self.assertEqual(fashion_contribs[0].value, self.expected_fashion)

    def test_scene_none_omits_fashion_but_keeps_walk(self) -> None:
        """scene=None: fashion not added; equipment walk + eager still added."""
        from world.checks.services import collect_check_modifiers

        breakdown = collect_check_modifiers(self.sheet, self.check_type, scene=None)

        self.assertEqual(breakdown.total, self.eager_value + self.expected_walk)

        equipment_contribs = self._contribs(breakdown, ModifierSourceKind.EQUIPMENT)
        labels = {c.source_label: c.value for c in equipment_contribs}
        self.assertEqual(labels.get("Equipment & attunement"), self.expected_walk)

        fashion_contribs = self._contribs(breakdown, ModifierSourceKind.FASHION)
        self.assertEqual(fashion_contribs, [])


class EquipmentWalkMockCheckTypeTests(TestCase):
    """A MagicMock check_type must not hit the DB (mirrors combat-resolver tests)."""

    def setUp(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        self.target = ObjectDBFactory(db_key="EquipWalkMockTarget")
        self.sheet = CharacterSheetFactory(character=self.target)

    def test_mock_check_type_does_not_raise_and_no_equipment(self) -> None:
        from unittest.mock import MagicMock

        from world.checks.services import collect_check_modifiers

        mock_check_type = MagicMock()
        breakdown = collect_check_modifiers(self.sheet, mock_check_type)
        equipment = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.EQUIPMENT
        ]
        self.assertEqual(equipment, [])
        self.assertEqual(breakdown.total, 0)
