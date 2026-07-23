"""Combat role bonus reads bond-adjusted level for mentor/sidekick (#1165, Task 7).

Spec: _combat_target_bonus computes bond_adjusted_level(sheet) to get the level
override, then passes it to get_modifier_total.  This makes:
  - A suppressed MENTOR's combat bonus lower than the same unbonded character's.
  - An elevated SIDEKICK's combat bonus higher than unbonded.
  - An UNBONDED character's combat bonus unchanged (bond_adjusted_level → None → current_level).
  - A NON-combat get_modifier_total (no override) also unchanged.

Scaffold: covenant at level 5, band [3, 7] (band_width=2).
  - Mentor: level 9 → out-of-band (above) → adjusted_party=MENTOR.
    bond_adjusted_level(mentor) = clamp(sidekick_raw + adjacency_offset, 3, 7)
                                = clamp(1 + 1, 3, 7) = 3.
    Unbonded mentor: level 9 → role_bonus = 9 * bonus_per_level.
    Bonded mentor:  level 3 → role_bonus = 3 * bonus_per_level.  (LOWER ✓)

  - Sidekick: level 1 → out-of-band (below) → adjusted_party=SIDEKICK.
    bond_adjusted_level(sidekick) = clamp(mentor_raw - adjacency_offset, 3, 7)
                                  = clamp(9 - 1, 3, 7) = 7.
    Unbonded sidekick: level 1 → role_bonus = 1 * bonus_per_level.
    Bonded sidekick:   level 7 → role_bonus = 7 * bonus_per_level.  (HIGHER ✓)
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.combat.factories import wire_weapon_damage_modifier_target
from world.combat.services import _combat_target_bonus
from world.covenants.constants import MentorBondAdjusted
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleBonusFactory,
    GearArchetypeCompatibilityFactory,
    MentorBondFactory,
    make_engaged_member,
    seed_mentor_bond_defaults,
)
from world.items.constants import (
    WEAPON_DAMAGE_TARGET_NAME,
    BodyRegion,
    EquipmentLayer,
    GearArchetype,
)
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.mechanics.services import get_modifier_total

BONUS_PER_LEVEL = 2
COVENANT_LEVEL = 5  # band [3, 7]
MENTOR_RAW_LEVEL = 9  # above band → MENTOR is adjusted
SIDEKICK_RAW_LEVEL = 1  # below band → SIDEKICK is adjusted


def _make_character_with_level(key: str, level: int):
    """Create a CharacterSheet with a primary class level row."""
    char = CharacterFactory(db_key=key)
    sheet = CharacterSheetFactory(character=char, primary_persona=False)
    char_class = CharacterClassFactory()
    CharacterClassLevelFactory(
        character=sheet, character_class=char_class, level=level, is_primary=True
    )
    sheet.invalidate_class_level_cache()
    assert sheet.current_level == level, f"Expected level {level}, got {sheet.current_level}"
    return char, sheet


def _equip_weapon(char):
    """Equip a compatible MELEE_ONE_HAND weapon on the character."""
    template = ItemTemplateFactory(
        gear_archetype=GearArchetype.MELEE_ONE_HAND,
        base_weapon_damage=5,
        max_durability=10,
    )
    item = ItemInstanceFactory(template=template, durability=10)
    EquippedItemFactory(
        character=char,
        item_instance=item,
        body_region=BodyRegion.RIGHT_HAND,
        equipment_layer=EquipmentLayer.BASE,
    )
    char.equipped_items.invalidate()
    return item


class MentorSuppressedCombatBonusTests(TestCase):
    """Bonded MENTOR has LOWER combat role bonus than the same character unbonded."""

    def setUp(self) -> None:
        seed_mentor_bond_defaults()  # band_width=2, adjacency_offset=1
        self.weapon_damage_target = wire_weapon_damage_modifier_target()

    def test_bonded_mentor_bonus_lower_than_unbonded(self) -> None:
        """Mentor at raw level 9, bonded to sidekick at level 1.

        bond_adjusted_level(mentor) = clamp(1 + 1, 3, 7) = 3.
        Unbonded level-9 bonus = 9 * 2 = 18.
        Bonded   level-3 bonus = 3 * 2 = 6.  (6 < 18 ✓)
        """
        covenant = CovenantFactory(level=COVENANT_LEVEL)

        # Mentor: level 9 (above band [3,7]) → adjusted_party=MENTOR.
        mentor_char, mentor_sheet = _make_character_with_level("MentorAdjusted9", MENTOR_RAW_LEVEL)
        membership = make_engaged_member(character_sheet=mentor_sheet)
        mentor_char.covenant_roles.invalidate()

        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role,
            modifier_target=self.weapon_damage_target,
            bonus_per_level=BONUS_PER_LEVEL,
        )
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role,
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
        )
        _equip_weapon(mentor_char)

        # Sidekick: level 1 (below band).
        _, sidekick_sheet = _make_character_with_level("SidekickForMentor", SIDEKICK_RAW_LEVEL)

        # Bind: mentor is out-of-band (level 9, above 7) → adjusted_party=MENTOR.
        MentorBondFactory(
            covenant=covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
            adjusted_party=MentorBondAdjusted.MENTOR,
            dissolved_at=None,
        )

        # Unbonded baseline: character at same level 9, no bond.
        unbonded_char, unbonded_sheet = _make_character_with_level(
            "UnbondedMentor9", MENTOR_RAW_LEVEL
        )
        unbonded_membership = make_engaged_member(character_sheet=unbonded_sheet)
        unbonded_char.covenant_roles.invalidate()
        CovenantRoleBonusFactory(
            covenant_role=unbonded_membership.covenant_role,
            modifier_target=self.weapon_damage_target,
            bonus_per_level=BONUS_PER_LEVEL,
        )
        GearArchetypeCompatibilityFactory(
            covenant_role=unbonded_membership.covenant_role,
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
        )
        _equip_weapon(unbonded_char)

        bonded_bonus = _combat_target_bonus(mentor_sheet, WEAPON_DAMAGE_TARGET_NAME)
        unbonded_bonus = _combat_target_bonus(unbonded_sheet, WEAPON_DAMAGE_TARGET_NAME)

        # Bonded mentor's effective level is 3, so bonus = 3*2 = 6.
        # Unbonded level-9 bonus = 9*2 = 18.
        self.assertEqual(bonded_bonus, 3 * BONUS_PER_LEVEL)
        self.assertEqual(unbonded_bonus, MENTOR_RAW_LEVEL * BONUS_PER_LEVEL)
        self.assertLess(bonded_bonus, unbonded_bonus)


class SidekickElevatedCombatBonusTests(TestCase):
    """Bonded SIDEKICK has HIGHER combat role bonus than the same character unbonded."""

    def setUp(self) -> None:
        seed_mentor_bond_defaults()  # band_width=2, adjacency_offset=1
        self.weapon_damage_target = wire_weapon_damage_modifier_target()

    def test_bonded_sidekick_bonus_higher_than_unbonded(self) -> None:
        """Sidekick at raw level 1, bonded to mentor at level 9.

        bond_adjusted_level(sidekick) = clamp(9 - 1, 3, 7) = 7.
        Unbonded level-1 bonus = 1 * 2 = 2.
        Bonded   level-7 bonus = 7 * 2 = 14.  (14 > 2 ✓)
        """
        covenant = CovenantFactory(level=COVENANT_LEVEL)

        # Sidekick: level 1 (below band [3,7]) → adjusted_party=SIDEKICK.
        sidekick_char, sidekick_sheet = _make_character_with_level(
            "SidekickAdjusted1", SIDEKICK_RAW_LEVEL
        )
        membership = make_engaged_member(character_sheet=sidekick_sheet)
        sidekick_char.covenant_roles.invalidate()

        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role,
            modifier_target=self.weapon_damage_target,
            bonus_per_level=BONUS_PER_LEVEL,
        )
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role,
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
        )
        _equip_weapon(sidekick_char)

        # Mentor: level 9 (in-band is the mentor's role here, sidekick is adjusted).
        _, mentor_sheet = _make_character_with_level("MentorForSidekick", MENTOR_RAW_LEVEL)

        # Bind: sidekick out-of-band (level 1, below 3) → adjusted_party=SIDEKICK.
        MentorBondFactory(
            covenant=covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
            adjusted_party=MentorBondAdjusted.SIDEKICK,
            dissolved_at=None,
        )

        # Unbonded baseline: character at same level 1, no bond.
        unbonded_char, unbonded_sheet = _make_character_with_level(
            "UnbondedSidekick1", SIDEKICK_RAW_LEVEL
        )
        unbonded_membership = make_engaged_member(character_sheet=unbonded_sheet)
        unbonded_char.covenant_roles.invalidate()
        CovenantRoleBonusFactory(
            covenant_role=unbonded_membership.covenant_role,
            modifier_target=self.weapon_damage_target,
            bonus_per_level=BONUS_PER_LEVEL,
        )
        GearArchetypeCompatibilityFactory(
            covenant_role=unbonded_membership.covenant_role,
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
        )
        _equip_weapon(unbonded_char)

        bonded_bonus = _combat_target_bonus(sidekick_sheet, WEAPON_DAMAGE_TARGET_NAME)
        unbonded_bonus = _combat_target_bonus(unbonded_sheet, WEAPON_DAMAGE_TARGET_NAME)

        # Bonded sidekick's effective level is 7, so bonus = 7*2 = 14.
        # Unbonded level-1 bonus = 1*2 = 2.
        self.assertEqual(bonded_bonus, 7 * BONUS_PER_LEVEL)
        self.assertEqual(unbonded_bonus, SIDEKICK_RAW_LEVEL * BONUS_PER_LEVEL)
        self.assertGreater(bonded_bonus, unbonded_bonus)


class UnbondedCombatBonusUnchangedTests(TestCase):
    """UNBONDED character's combat bonus is unchanged (bond_adjusted_level → None)."""

    def setUp(self) -> None:
        seed_mentor_bond_defaults()
        self.weapon_damage_target = wire_weapon_damage_modifier_target()

    def test_unbonded_combat_bonus_equals_level_based_result(self) -> None:
        """An unbonded character: _combat_target_bonus == get_modifier_total with no override.

        bond_adjusted_level returns None → falls through to current_level.
        Both paths must produce identical results.
        """
        char, sheet = _make_character_with_level("UnbondedChar5", 5)
        membership = make_engaged_member(character_sheet=sheet)
        char.covenant_roles.invalidate()

        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role,
            modifier_target=self.weapon_damage_target,
            bonus_per_level=BONUS_PER_LEVEL,
        )
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role,
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
        )
        _equip_weapon(char)

        # No bond created for this character.
        combat_bonus = _combat_target_bonus(sheet, WEAPON_DAMAGE_TARGET_NAME)
        non_combat_bonus = get_modifier_total(sheet, self.weapon_damage_target)

        # Both should equal level * bonus_per_level = 5 * 2 = 10.
        self.assertEqual(combat_bonus, 5 * BONUS_PER_LEVEL)
        self.assertEqual(combat_bonus, non_combat_bonus)


class NonCombatPathUnchangedTests(TestCase):
    """NON-combat get_modifier_total (no override) is unchanged regardless of bond state."""

    def setUp(self) -> None:
        seed_mentor_bond_defaults()
        self.weapon_damage_target = wire_weapon_damage_modifier_target()

    def test_non_combat_modifier_total_uses_current_level_not_bond(self) -> None:
        """get_modifier_total (no level_override) always uses sheet.current_level.

        Even if a bond would adjust the level in combat, the non-combat path must
        return current_level * bonus_per_level (no bond lookup, no override).
        """
        covenant = CovenantFactory(level=COVENANT_LEVEL)

        # Sidekick at level 1 with an active bond.
        sidekick_char, sidekick_sheet = _make_character_with_level(
            "NonCombatSidekick1", SIDEKICK_RAW_LEVEL
        )
        membership = make_engaged_member(character_sheet=sidekick_sheet)
        sidekick_char.covenant_roles.invalidate()

        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role,
            modifier_target=self.weapon_damage_target,
            bonus_per_level=BONUS_PER_LEVEL,
        )
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role,
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
        )
        _equip_weapon(sidekick_char)

        _, mentor_sheet = _make_character_with_level("NonCombatMentor9", MENTOR_RAW_LEVEL)
        MentorBondFactory(
            covenant=covenant,
            mentor_sheet=mentor_sheet,
            sidekick_sheet=sidekick_sheet,
            adjusted_party=MentorBondAdjusted.SIDEKICK,
            dissolved_at=None,
        )

        # Non-combat path: no level_override → must use current_level=1, not bond-adjusted 7.
        non_combat = get_modifier_total(sidekick_sheet, self.weapon_damage_target)
        self.assertEqual(non_combat, SIDEKICK_RAW_LEVEL * BONUS_PER_LEVEL)

        # Combat path: bond adjusts level to 7.
        combat = _combat_target_bonus(sidekick_sheet, WEAPON_DAMAGE_TARGET_NAME)
        self.assertEqual(combat, 7 * BONUS_PER_LEVEL)

        # They differ — the non-combat path is insulated from the bond.
        self.assertNotEqual(non_combat, combat)
