"""End-to-end integration tests for gear compatibility pipeline (Spec D §5.6).

Pipeline: CharacterSheet + CovenantRole + GearArchetypeCompatibility (for compatible archetype
only) → patch placeholder helpers (role_base_bonus_for_target, item_mundane_stat_for_target) →
call get_modifier_total(sheet, target) → assert additive-vs-max branching.

Math reference:
  compatible gear:   role_bonus + gear_stat  (additive)
  incompatible gear: max(role_bonus, gear_stat)
  two items (one each): (role+gear) + max(role, gear)

The PR1 placeholders return 0. All five tests patch them to non-zero values so the
branching logic fires at the integration level rather than collapsing to a trivial 0.

Category "stat" is in EQUIPMENT_RELEVANT_CATEGORIES, so the equipment walk fires.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase


class GearCompatibilityPipelineTests(TestCase):
    """Happy-path and branching tests driving get_modifier_total end-to-end.

    All shared rows live in setUpTestData. Per-test patches are applied inline
    with unittest.mock.patch so they do not bleed across methods.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            GearArchetypeCompatibilityFactory,
        )
        from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
        )
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        # 1. Character + CharacterSheet
        cls.character_obj = CharacterFactory(db_key="GearCompatPipelineChar")
        cls.sheet = CharacterSheetFactory(character=cls.character_obj, primary_persona=False)

        # 2. ModifierCategory in EQUIPMENT_RELEVANT_CATEGORIES + ModifierTarget
        #    "stat" is in EQUIPMENT_RELEVANT_CATEGORIES so the equipment walk fires.
        cls.category = ModifierCategoryFactory(name="stat")
        cls.target = ModifierTargetFactory(
            name="GearCompatPipelineTarget",
            category=cls.category,
        )

        # 3. CharacterCovenantRole assignment
        cls.assignment = CharacterCovenantRoleFactory(character_sheet=cls.sheet)
        cls.sheet.character.covenant_roles.invalidate()

        # 4. Compatible item template: HEAVY_ARMOR, slotted at TORSO/BASE
        cls.compat_template = ItemTemplateFactory(
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )
        cls.compat_item = ItemInstanceFactory(template=cls.compat_template)
        cls.compat_equipped = EquippedItemFactory(
            character=cls.character_obj,
            item_instance=cls.compat_item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # 5. Incompatible item template: RANGED, slotted at RIGHT_HAND/BASE
        cls.incompat_template = ItemTemplateFactory(
            gear_archetype=GearArchetype.RANGED,
        )
        cls.incompat_item = ItemInstanceFactory(template=cls.incompat_template)
        cls.incompat_equipped = EquippedItemFactory(
            character=cls.character_obj,
            item_instance=cls.incompat_item,
            body_region=BodyRegion.RIGHT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )

        # 6. GearArchetypeCompatibility for HEAVY_ARMOR only — RANGED intentionally absent
        GearArchetypeCompatibilityFactory(
            covenant_role=cls.assignment.covenant_role,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )

        # 7. Invalidate caches so both equipped items are visible
        cls.character_obj.equipped_items.invalidate()

    # ------------------------------------------------------------------
    # Helpers: fresh single-item characters to avoid slot conflicts
    # ------------------------------------------------------------------

    @classmethod
    def _make_single_compat_sheet(cls) -> object:
        """Return a fresh sheet with only the HEAVY_ARMOR (compatible) item equipped."""
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            GearArchetypeCompatibilityFactory,
        )
        from world.items.constants import GearArchetype
        from world.items.factories import EquippedItemFactory, ItemInstanceFactory

        char = CharacterFactory(db_key="SingleCompatChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        assignment = CharacterCovenantRoleFactory(character_sheet=sheet)
        char.covenant_roles.invalidate()

        item = ItemInstanceFactory(template=cls.compat_template)
        EquippedItemFactory(character=char, item_instance=item)
        char.equipped_items.invalidate()

        GearArchetypeCompatibilityFactory(
            covenant_role=assignment.covenant_role,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )
        return sheet

    @classmethod
    def _make_single_incompat_sheet(cls) -> object:
        """Return a fresh sheet with only the RANGED (incompatible) item equipped."""
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import CharacterCovenantRoleFactory
        from world.items.factories import EquippedItemFactory, ItemInstanceFactory

        char = CharacterFactory(db_key="SingleIncompatChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        CharacterCovenantRoleFactory(character_sheet=sheet)
        char.covenant_roles.invalidate()

        item = ItemInstanceFactory(template=cls.incompat_template)
        EquippedItemFactory(character=char, item_instance=item)
        char.equipped_items.invalidate()
        # No GearArchetypeCompatibility row — RANGED is intentionally absent
        return sheet

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_compatible_gear_additive(self) -> None:
        """Patches: role=10, gear=3. Single compatible item (HEAVY_ARMOR) → 10+3 = 13."""
        from world.mechanics.services import get_modifier_total

        sheet = self._make_single_compat_sheet()

        with (
            patch("world.mechanics.services.role_base_bonus_for_target", return_value=10),
            patch("world.mechanics.services.item_mundane_stat_for_target", return_value=3),
        ):
            result = get_modifier_total(sheet, self.target)

        self.assertEqual(result, 13)  # 10 + 3 additive

    def test_incompatible_gear_max(self) -> None:
        """Patches: role=10, gear=3. Single incompatible item (RANGED) → max(10, 3) = 10."""
        from world.mechanics.services import get_modifier_total

        sheet = self._make_single_incompat_sheet()

        with (
            patch("world.mechanics.services.role_base_bonus_for_target", return_value=10),
            patch("world.mechanics.services.item_mundane_stat_for_target", return_value=3),
        ):
            result = get_modifier_total(sheet, self.target)

        self.assertEqual(result, 10)  # max(10, 3)

    def test_two_items_compatible_and_incompatible_aggregate(self) -> None:
        """Patches: role=5, gear=2. One compatible + one incompatible → (5+2) + max(5,2) = 12."""
        from world.mechanics.services import get_modifier_total

        with (
            patch("world.mechanics.services.role_base_bonus_for_target", return_value=5),
            patch("world.mechanics.services.item_mundane_stat_for_target", return_value=2),
        ):
            result = get_modifier_total(self.sheet, self.target)

        self.assertEqual(result, 12)  # (5+2) + max(5,2) = 7 + 5

    def test_no_role_returns_zero(self) -> None:
        """No CharacterCovenantRole row → covenant_role_bonus returns 0 → total is 0."""
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.constants import GearArchetype
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
        )
        from world.mechanics.services import get_modifier_total

        char = CharacterFactory(db_key="NoRoleGearPipelineChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        # No CharacterCovenantRole — currently_held() will return None
        item = ItemInstanceFactory(
            template=ItemTemplateFactory(gear_archetype=GearArchetype.HEAVY_ARMOR)
        )
        EquippedItemFactory(character=char, item_instance=item)
        char.equipped_items.invalidate()

        with (
            patch("world.mechanics.services.role_base_bonus_for_target", return_value=10),
            patch("world.mechanics.services.item_mundane_stat_for_target", return_value=3),
        ):
            result = get_modifier_total(sheet, self.target)

        self.assertEqual(result, 0)

    def test_incompatible_gear_higher_max_wins(self) -> None:
        """Patches: role=2, gear=15. Incompatible item → max(2, 15) = 15."""
        from world.mechanics.services import get_modifier_total

        sheet = self._make_single_incompat_sheet()

        with (
            patch("world.mechanics.services.role_base_bonus_for_target", return_value=2),
            patch("world.mechanics.services.item_mundane_stat_for_target", return_value=15),
        ):
            result = get_modifier_total(sheet, self.target)

        self.assertEqual(result, 15)  # max(2, 15)
