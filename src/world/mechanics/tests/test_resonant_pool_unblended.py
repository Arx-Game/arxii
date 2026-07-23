"""Un-blended resonant-pool primitives for the armor-soak seam (#1174).

covenant_role_base_total returns the raw engaged-role bonus (Σ level × bonus_per_level),
with NO per-gear subtraction — unlike covenant_role_bonus, which blends per equipped slot.
equipment_walk_total_unblended swaps that raw base in for the role component so the soak
seam can pool all resonant soak before its compatible-additive / incompatible-max blend.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.combat.factories import wire_armor_soak_modifier_target
from world.covenants.factories import (
    CovenantRoleBonusFactory,
    GearArchetypeCompatibilityFactory,
    make_engaged_member,
)
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.mechanics.services import covenant_role_base_total, equipment_walk_total_unblended


class CovenantRoleBaseTotalTests(TestCase):
    def _level2_covenant_char(self):
        char = CharacterFactory(db_key="RoleBaseChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet, character_class=char_class, level=2)
        sheet.invalidate_class_level_cache()
        membership = make_engaged_member(character_sheet=sheet)
        char.covenant_roles.invalidate()
        return char, sheet, membership

    def test_returns_raw_role_bonus_ignoring_gear(self) -> None:
        """Raw base = level * bonus_per_level, regardless of equipped gear (no subtraction)."""
        char, sheet, membership = self._level2_covenant_char()
        target = wire_armor_soak_modifier_target()
        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role, modifier_target=target, bonus_per_level=2
        )
        # Equip incompatible heavy armor with high soak — must NOT reduce the raw base.
        template = ItemTemplateFactory(
            gear_archetype=GearArchetype.HEAVY_ARMOR, base_armor_soak=99, max_durability=30
        )
        inst = ItemInstanceFactory(template=template, durability=30)
        EquippedItemFactory(
            character=char,
            item_instance=inst,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        char.equipped_items.invalidate()
        # Raw base = 2 * 2 = 4, untouched by the gear_stat=99.
        self.assertEqual(covenant_role_base_total(sheet, target), 4)

    def test_zero_when_no_engaged_role(self) -> None:
        char = CharacterFactory(db_key="NoRoleBaseChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        target = wire_armor_soak_modifier_target()
        self.assertEqual(covenant_role_base_total(sheet, target), 0)


class EquipmentWalkUnblendedTests(TestCase):
    def test_uses_raw_role_base_not_blended(self) -> None:
        """For a compatible role the unblended walk equals the raw role base (other sources 0)."""
        char = CharacterFactory(db_key="UnblendedChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet, character_class=char_class, level=3)
        sheet.invalidate_class_level_cache()
        target = wire_armor_soak_modifier_target()
        membership = make_engaged_member(character_sheet=sheet)
        char.covenant_roles.invalidate()
        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role, modifier_target=target, bonus_per_level=2
        )
        template = ItemTemplateFactory(
            gear_archetype=GearArchetype.HEAVY_ARMOR, base_armor_soak=10, max_durability=30
        )
        inst = ItemInstanceFactory(template=template, durability=30)
        EquippedItemFactory(
            character=char,
            item_instance=inst,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        char.equipped_items.invalidate()
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role, gear_archetype=GearArchetype.HEAVY_ARMOR
        )
        # raw base = 3 * 2 = 6; facet/mantle/motif/covenant-level = 0.
        self.assertEqual(equipment_walk_total_unblended(sheet, target), 6)
