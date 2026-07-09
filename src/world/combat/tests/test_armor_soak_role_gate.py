"""Covenant-role armor-soak gate: compatible-additive / incompatible-max blend (#1174).

physical = Σ worn-armor effective_armor_soak, split by role compatibility.
resonant = un-blended resonant pool (role base + facet + mantle + motif + covenant-level).
soak = compat_physical + max(incompat_physical, resonant).
Durability wears only armor whose physical soak contributes to the final soak.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.combat.factories import wire_armor_soak_modifier_target
from world.combat.services import apply_equipped_armor_soak
from world.covenants.factories import (
    CovenantRoleBonusFactory,
    GearArchetypeCompatibilityFactory,
    make_engaged_member,
)
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory


class ArmorSoakRoleGateTests(TestCase):
    def _covenant_char(self, level: int, bonus_per_level: int, db_key: str):
        char = CharacterFactory(db_key=db_key)
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=char, character_class=char_class, level=level)
        sheet.invalidate_class_level_cache()
        target = wire_armor_soak_modifier_target()
        membership = make_engaged_member(character_sheet=sheet)
        char.covenant_roles.invalidate()
        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role,
            modifier_target=target,
            bonus_per_level=bonus_per_level,
        )
        return char, sheet, membership

    def _equip(self, char, archetype, base_soak, name, durability=30):
        template = ItemTemplateFactory(
            gear_archetype=archetype,
            base_armor_soak=base_soak,
            max_durability=durability,
            name=name,
        )
        inst = ItemInstanceFactory(template=template, durability=durability)
        EquippedItemFactory(
            character=char,
            item_instance=inst,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        char.equipped_items.invalidate()
        return inst

    def test_incompatible_low_level_physical_wins(self) -> None:
        """Level 1 incompatible heavy armor: physical platemail can still dominate.

        resonant = 1 * 4 = 4; physical (incompatible) = 10. soak = max(10, 4) = 10.
        damage 20 -> 10.
        """
        char, _, _ = self._covenant_char(level=1, bonus_per_level=4, db_key="LowLvlIncompat")
        self._equip(char, GearArchetype.HEAVY_ARMOR, 10, "LowPlate")  # no compat row → incompatible
        self.assertEqual(apply_equipped_armor_soak(char, 20).damage, 10)

    def test_incompatible_high_level_resonant_wins(self) -> None:
        """Level 3 incompatible heavy armor: resonant battle-lingerie beats platemail.

        resonant = 3 * 4 = 12; physical (incompatible) = 10. soak = max(10, 12) = 12.
        damage 20 -> 8.
        """
        char, _, _ = self._covenant_char(level=3, bonus_per_level=4, db_key="HighLvlIncompat")
        self._equip(char, GearArchetype.HEAVY_ARMOR, 10, "HighPlate")
        self.assertEqual(apply_equipped_armor_soak(char, 20).damage, 8)

    def test_compatible_is_additive(self) -> None:
        """Compatible role: armor AND resonant both apply.

        compat_physical = 3; resonant = 2 * 2 = 4; soak = 3 + max(0, 4) = 7. damage 20 -> 13.
        Matches the prior compatible-soak behavior.
        """
        char, _, membership = self._covenant_char(level=2, bonus_per_level=2, db_key="CompatChar")
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role, gear_archetype=GearArchetype.LIGHT_ARMOR
        )
        self._equip(char, GearArchetype.LIGHT_ARMOR, 3, "CompatArmor")
        self.assertEqual(apply_equipped_armor_soak(char, 20).damage, 13)

    def test_non_covenant_armor_only(self) -> None:
        """No engaged role: resonant = 0; soak = max(physical, 0) = physical."""
        char = CharacterFactory(db_key="NonCovGate")
        CharacterSheetFactory(character=char, primary_persona=False)
        wire_armor_soak_modifier_target()
        self._equip(char, GearArchetype.LIGHT_ARMOR, 4, "NonCovArmor")
        self.assertEqual(apply_equipped_armor_soak(char, 20).damage, 16)

    def test_incompatible_armor_not_worn_when_resonant_dominates(self) -> None:
        """When resonant beats incompatible armor, that armor does not lose durability."""
        char, _, _ = self._covenant_char(level=3, bonus_per_level=4, db_key="NoWearChar")
        inst = self._equip(char, GearArchetype.HEAVY_ARMOR, 10, "IgnoredPlate", durability=30)
        apply_equipped_armor_soak(char, 20)  # resonant 12 > physical 10 → plate ignored
        inst.refresh_from_db()
        self.assertEqual(inst.durability, 30)

    def test_incompatible_armor_worn_when_physical_dominates(self) -> None:
        """When incompatible armor wins the max, it does lose durability."""
        char, _, _ = self._covenant_char(level=1, bonus_per_level=4, db_key="WearChar")
        inst = self._equip(char, GearArchetype.HEAVY_ARMOR, 10, "UsedPlate", durability=30)
        apply_equipped_armor_soak(char, 20)  # physical 10 > resonant 4 → plate used
        inst.refresh_from_db()
        self.assertLess(inst.durability, 30)
