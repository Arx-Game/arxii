"""Spec D acceptance gate (#512) — craft → wear → combat, end-to-end.

This is the issue's integration acceptance test. It walks the WHOLE Mantle
narrative through the REAL service entry points (not factory shortcuts where a
service exists), proving the chain composes:

    craft a mantle-bearing item
      → attune it (real codex clearance recorder + real weave gate)
        → wear it (real ``equip_item`` service)
          → enter a combat scene whose realm society sets the fashion
            → ``collect_check_modifiers`` (the seam combat funnels through)

surfaces a MANTLE-derived bonus (via the EQUIPMENT "Equipment & attunement"
source), a FASHION-kind contribution, and the eager CharacterModifier — with an
exact integer total that proves nothing is double-counted.

Real service entry points exercised:
  * ``record_mantle_clearances`` (items.services.mantle) — codex → clearance rows.
    Also invoked transitively by the weave gate.
  * ``weave_thread`` (magic.services) with ``TargetKind.MANTLE`` — the gated weave
    entry point; raises ``MantleNotClearedError`` until a clearance exists.
  * ``equip_item`` (items.services.equip) — the real wear path.
  * ``collect_check_modifiers`` (checks.services) — the combat modifier seam.

Single ModifierTarget linked three ways (mirrors Task 7's equipment-walk test):
  * ``category.name == "resonance"`` → in EQUIPMENT_RELEVANT_CATEGORIES, so the
    equipment walk runs;
  * ``target_resonance`` → the mantle passive walk gates true;
  * ``target_check_type`` → ``collect_check_modifiers`` resolves it as the scoped
    target for the combat CheckType.

Known-integer math (asserted exactly, to prove no double count):
  * eager CharacterModifier value                                = 10
  * mantle:  flat 7 × max(1, woven thread level 0) = 7 × 1       = 7
  * fashion: FASHION_MATCH_BASE 1 × item 1.0 × attach 1.0 × weight 2 = 2
  → CHARACTER (eager) 10 + EQUIPMENT walk (mantle 7) + FASHION 2 = 19

``weave_thread`` creates the Thread at ``level=0``; the mantle walk uses
``max(1, level)`` so the multiplier is 1 — this is the realistic just-attuned
state (no Imbuing yet).
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.checks.constants import ModifierSourceKind


class MantleCombatPipelineTests(TestCase):
    """A player crafts, attunes and wears a mantle, then fights — all real services."""

    @classmethod
    def setUpTestData(cls) -> None:  # noqa: PLR0915 - end-to-end fixture spans many rows
        from evennia.objects.models import ObjectDB

        from evennia_extensions.factories import CharacterFactory
        from world.areas.constants import AreaLevel
        from world.areas.factories import AreaFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
        from world.codex.constants import CodexKnowledgeStatus
        from world.codex.factories import (
            CharacterCodexKnowledgeFactory,
            CodexEntryFactory,
        )
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import (
            FashionStyleBonusFactory,
            FashionStyleFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            MantleFactory,
            MantleLevelDefinitionFactory,
            QualityTierFactory,
            TemplateSlotFactory,
        )
        from world.magic.constants import EffectKind, TargetKind
        from world.magic.factories import FacetFactory, ResonanceFactory, ThreadPullEffectFactory
        from world.mechanics.factories import (
            CharacterModifierFactory,
            DistinctionModifierSourceFactory,
            ModifierCategoryFactory,
            ModifierTargetFactory,
        )
        from world.realms.models import Realm
        from world.roster.factories import RosterEntryFactory
        from world.scenes.factories import SceneFactory

        # --- Expected math (see module docstring) ---
        cls.eager_value = 10
        cls.expected_mantle = 7
        cls.expected_fashion = 2
        cls.expected_total = cls.eager_value + cls.expected_mantle + cls.expected_fashion  # 19

        # --- Character + sheet + roster entry (codex knowledge lives on roster) ---
        cls.character_obj = CharacterFactory(db_key="MantleCombatChar")
        cls.sheet = CharacterSheetFactory(character=cls.character_obj, primary_persona=False)
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)

        # --- Resonance the mantle thread channels (and the target is keyed to) ---
        cls.resonance = ResonanceFactory()

        # --- Combat CheckType + scoped ModifierTarget (resonance category, linked 3 ways) ---
        cls.combat_category = CheckCategoryFactory(name="Combat")
        cls.check_type = CheckTypeFactory(name="MantleCombatStrike", category=cls.combat_category)
        cls.resonance_category = ModifierCategoryFactory(name="resonance")
        cls.target = ModifierTargetFactory(
            name="mantle_combat_target",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
            target_check_type=cls.check_type,
        )

        # --- Eager CharacterModifier on the scoped target (the CHARACTER row) ---
        source = DistinctionModifierSourceFactory(distinction_effect__target=cls.target)
        cls.eager_modifier = CharacterModifierFactory(
            character=cls.sheet, value=cls.eager_value, source=source, target=cls.target
        )

        # =====================================================================
        # 1. CRAFT — a specific mantle-bearing item with a facet attached.
        # =====================================================================
        cls.unit_quality = QualityTierFactory(
            name="MantleCombatUnitQ", stat_multiplier=Decimal("1.00")
        )
        cls.mantle_facet = FacetFactory(name="MantleCombatFacet")
        cls.template = ItemTemplateFactory(name="MantleCombatRegalia", facet_capacity=1)
        TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        # The crafted item instance — Mantle and ItemFacet both hang off THIS row.
        cls.mantle_item = ItemInstanceFactory(template=cls.template, quality_tier=cls.unit_quality)
        cls.item_facet = ItemFacetFactory(
            item_instance=cls.mantle_item,
            facet=cls.mantle_facet,
            attachment_quality_tier=cls.unit_quality,
        )
        # The Mantle on the crafted item, gated at level 1 by a codex entry.
        cls.mantle = MantleFactory(name="MantleCombatRegaliaMantle", item_instance=cls.mantle_item)
        cls.codex_entry = CodexEntryFactory(name="Mantle Combat Lore I")
        cls.level_def = MantleLevelDefinitionFactory(
            mantle=cls.mantle, level=1, codex_entry_required=cls.codex_entry
        )

        # =====================================================================
        # 2. ATTUNE — learn the codex entry; the authored passive effect waits
        #    for the thread (woven in setUp, after a negative-leg assertion).
        # =====================================================================
        CharacterCodexKnowledgeFactory(
            roster_entry=cls.roster_entry,
            entry=cls.codex_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        # Tier-0 always-on FLAT_BONUS for the combat target via the mantle thread.
        ThreadPullEffectFactory(
            target_kind=TargetKind.MANTLE,
            resonance=cls.resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=cls.expected_mantle,
        )

        # =====================================================================
        # 4. COMBAT SCENE — area whose realm society sets the current fashion;
        #    the crafted item's facet is in vogue so fashion fires.
        # =====================================================================
        cls.style = FashionStyleFactory(name="MantleCombatStyle")
        cls.style.in_vogue_facets.add(cls.mantle_facet)
        FashionStyleBonusFactory(fashion_style=cls.style, target=cls.target, weight=2)

        from world.societies.factories import SocietyFactory

        cls.realm = Realm.objects.create(name="MantleCombatRealm")
        cls.society = SocietyFactory(
            name="MantleCombatSociety",
            realm=cls.realm,
            current_fashion_style=cls.style,
        )
        cls.area = AreaFactory(
            name="MantleCombatArea",
            level=AreaLevel.WARD,
            realm=cls.realm,
            dominant_society=cls.society,
        )
        cls.room_obj = ObjectDB.objects.create(
            db_key="MantleCombatRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        from evennia_extensions.models import RoomProfile

        RoomProfile.objects.update_or_create(objectdb=cls.room_obj, defaults={"area": cls.area})
        cls.scene = SceneFactory(location=cls.room_obj)

    def setUp(self) -> None:
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.services.equip import equip_item

        # Handler caches live on the idmapper-shared Character and leak across
        # test methods; invalidate so each walk re-reads setUpTestData rows.
        self.character_obj.threads.invalidate()
        self.character_obj.equipped_items.invalidate()
        self.character_obj.mantle_clearances.invalidate()

        # =================================================================
        # 3. WEAR — equip the crafted mantle item via the real service.
        # =================================================================
        equip_item(
            character_sheet=self.sheet,
            item_instance=self.mantle_item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

    def tearDown(self) -> None:
        from world.items.models import EquippedItem
        from world.magic.models import Thread

        EquippedItem.objects.filter(character=self.character_obj).delete()
        Thread.objects.filter(owner=self.sheet).delete()
        self.character_obj.equipped_items.invalidate()
        self.character_obj.threads.invalidate()
        self.character_obj.mantle_clearances.invalidate()

    def _contribs(self, breakdown, kind):
        return [c for c in breakdown.contributions if c.source_kind == kind]

    def _attune(self):
        """Run the REAL attune chain: record clearances, then weave the MANTLE thread.

        ``weave_thread`` itself re-runs ``record_mantle_clearances`` and enforces
        the clearance gate, so this exercises both real entry points.
        """
        from world.items.services.mantle import record_mantle_clearances
        from world.magic.constants import TargetKind
        from world.magic.services import weave_thread

        created = record_mantle_clearances(self.sheet, self.mantle)
        self.character_obj.mantle_clearances.invalidate()
        thread = weave_thread(
            self.sheet,
            TargetKind.MANTLE,
            self.mantle,
            self.resonance,
            name="Banner of the Crafted Regalia",
        )
        self.character_obj.threads.invalidate()
        return created, thread

    def test_attune_records_clearance_and_weaves_thread(self) -> None:
        """The real clearance recorder + weave gate produce a MANTLE thread."""
        from world.items.models import MantleLevelClearance
        from world.magic.constants import TargetKind
        from world.magic.models import Thread

        created, thread = self._attune()

        # Clearance row appeared for the cleared level.
        self.assertEqual([c.level for c in created], [1])
        self.assertTrue(
            MantleLevelClearance.objects.filter(
                character_sheet=self.sheet, mantle=self.mantle, level=1
            ).exists()
        )

        # Thread exists with the MANTLE discriminator + typed FK set.
        self.assertEqual(thread.target_kind, TargetKind.MANTLE)
        self.assertEqual(thread.target_mantle, self.mantle)
        self.assertEqual(thread.owner, self.sheet)
        self.assertEqual(thread.resonance, self.resonance)
        self.assertTrue(
            Thread.objects.filter(
                owner=self.sheet, target_kind=TargetKind.MANTLE, target_mantle=self.mantle
            ).exists()
        )

    def test_before_attunement_no_mantle_bonus(self) -> None:
        """Negative leg: with the item worn but NOT attuned, no mantle bonus surfaces.

        Proves the attunement (the woven thread) is what surfaces the mantle
        bonus — the equipped item alone does not. Fashion still fires (it depends
        on the worn facet, not the thread); the eager CharacterModifier remains.
        """
        from world.checks.services import collect_check_modifiers

        breakdown = collect_check_modifiers(self.sheet, self.check_type, scene=self.scene)

        equipment_contribs = self._contribs(breakdown, ModifierSourceKind.EQUIPMENT)
        labels = {c.source_label: c.value for c in equipment_contribs}
        # No mantle thread → the equipment walk contributes nothing.
        self.assertEqual(labels.get("Equipment & attunement", 0), 0)

        # Eager + fashion still present; mantle absent from the total.
        self.assertEqual(breakdown.total, self.eager_value + self.expected_fashion)

    def test_full_pipeline_surfaces_mantle_fashion_and_eager(self) -> None:
        """After attunement: eager + mantle walk + fashion, exact total, no double count."""
        from world.checks.services import collect_check_modifiers

        self._attune()

        breakdown = collect_check_modifiers(self.sheet, self.check_type, scene=self.scene)

        # Exact total proves NO double-count of the eager CharacterModifier total.
        self.assertEqual(breakdown.total, self.expected_total)

        # Eager CharacterModifier counted exactly once.
        character_contribs = self._contribs(breakdown, ModifierSourceKind.CHARACTER)
        self.assertEqual(len(character_contribs), 1)
        self.assertEqual(character_contribs[0].value, self.eager_value)

        # MANTLE-derived bonus via the EQUIPMENT "Equipment & attunement" source.
        equipment_contribs = self._contribs(breakdown, ModifierSourceKind.EQUIPMENT)
        labels = {c.source_label: c.value for c in equipment_contribs}
        self.assertEqual(labels.get("Equipment & attunement"), self.expected_mantle)

        # FASHION-kind contribution present.
        fashion_contribs = self._contribs(breakdown, ModifierSourceKind.FASHION)
        self.assertEqual(len(fashion_contribs), 1)
        self.assertEqual(fashion_contribs[0].value, self.expected_fashion)
