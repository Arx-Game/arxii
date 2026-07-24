"""Integration + regression tests: covenant-role armor-soak gate in combat seams (#985, #1174).

Four test classes:
  (a) Full-chain modifier-total: get_modifier_total(sheet, weapon_damage_target) equals the
      covenant-role marginal bonus (character_level * bonus_per_level) for a compatible weapon.
  (b) Soak seam: apply_equipped_armor_soak computes
      compat_physical + max(incompat_physical, resonant).
  (c) Non-covenant regression guard: no engaged role → resonant pool = 0, soak = armor only.
  (d) Unseeded-target guard: _combat_target_bonus returns 0 when ModifierTarget row absent.

Design notes on the blend (#1174):
  - apply_equipped_armor_soak splits worn armor into compatible vs incompatible buckets via
    _split_armor_soak_by_compatibility (one bucket per GearArchetypeCompatibility existence check).
  - The resonant pool (_resonant_armor_soak) = eager CharacterModifier total +
    equipment_walk_total_unblended(sheet, armor_soak_target); the latter sums facet + mantle +
    motif-style + covenant_role_base_total (role base × level, un-blended, once per character).
  - Final soak = compat_physical + max(incompat_physical, resonant).
  - For a non-covenant character, equipment_walk_total_unblended = 0 for armor_soak_target (no
    facet threads, no role), so the resonant pool = 0 and soak reduces to armor-only.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.combat.factories import (
    wire_armor_soak_modifier_target,
    wire_weapon_damage_modifier_target,
)
from world.combat.services import _combat_target_bonus, apply_equipped_armor_soak
from world.covenants.factories import (
    CovenantRoleBonusFactory,
    GearArchetypeCompatibilityFactory,
    make_engaged_member,
)
from world.items.constants import (
    WEAPON_DAMAGE_TARGET_NAME,
    BodyRegion,
    EquipmentLayer,
    GearArchetype,
)
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.mechanics.services import get_modifier_total


class CovenantWeaponDamageFullChainTests(TestCase):
    """(a) Full-chain: get_modifier_total(sheet, weapon_damage_target) includes role bonus."""

    def test_compatible_weapon_modifier_total_equals_role_bonus(self) -> None:
        """With seeded target, engaged role, compatible weapon + compat row, level 2:
        get_modifier_total = character_level * bonus_per_level (marginal role bonus only).

        For compatible gear, covenant_role_bonus returns role_bonus stacked ON TOP of the
        raw gear stat (which is already counted in combat). So equipment_walk_total = role_bonus,
        and get_modifier_total = eager(0) + role_bonus = level * bonus_per_level = 2 * 3 = 6.
        """
        char = CharacterFactory(db_key="FullChainWeaponChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)

        # Set character level to 2 so role_base_bonus_for_target returns level * bonus_per_level.
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet, character_class=char_class, level=2)
        sheet.invalidate_class_level_cache()
        self.assertEqual(sheet.current_level, 2)

        weapon_damage_target = wire_weapon_damage_modifier_target()

        membership = make_engaged_member(character_sheet=sheet)
        char.covenant_roles.invalidate()

        # Author CovenantRoleBonus: bonus_per_level=3; level=2 → role_bonus = 6.
        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role,
            modifier_target=weapon_damage_target,
            bonus_per_level=3,
        )

        # Equip a compatible weapon: MELEE_ONE_HAND, base_weapon_damage=5.
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

        # Compatible archetype row → role_bonus stacks on top of what combat already counts.
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role,
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
        )

        total = get_modifier_total(sheet, weapon_damage_target)
        expected_role_bonus = 2 * 3  # character_level * bonus_per_level = 6
        # equipment_walk_total = covenant_role_bonus = role_bonus (compatible gear, one item).
        self.assertEqual(total, expected_role_bonus)


class CovenantArmorSoakSeamTests(TestCase):
    """(b) Soak seam: apply_equipped_armor_soak uses armor_soak + covenant_soak_bonus."""

    def _equip_armor(self, character, base_soak: int, name: str = "SoakArmor"):
        template = ItemTemplateFactory(
            gear_archetype=GearArchetype.LIGHT_ARMOR,
            base_armor_soak=base_soak,
            max_durability=30,
            name=name,
        )
        inst = ItemInstanceFactory(template=template, durability=30)
        EquippedItemFactory(
            character=character,
            item_instance=inst,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        character.equipped_items.invalidate()
        return inst

    def test_covenant_soak_bonus_reduces_damage_beyond_armor(self) -> None:
        """With armor_soak=3 + compatible role at level 2 + bonus_per_level=2:
        effective soak = 3 (compat_physical) + max(0, resonant=4) = 7; damage = 20 - 7 = 13.

        resonant = equipment_walk_total_unblended(sheet, armor_soak_target)
        = covenant_role_base_total = role_base × level = 2 * 2 = 4.
        compat_physical = 3 (armor is compatible); incompat_physical = 0.
        soak = 3 + max(0, 4) = 7.
        """
        char = CharacterFactory(db_key="CovenantSoakChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)

        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet, character_class=char_class, level=2)
        sheet.invalidate_class_level_cache()

        armor_soak_target = wire_armor_soak_modifier_target()

        membership = make_engaged_member(character_sheet=sheet)
        char.covenant_roles.invalidate()

        # bonus_per_level=2, level=2 → role_bonus = 4.
        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role,
            modifier_target=armor_soak_target,
            bonus_per_level=2,
        )

        # Compatible archetype row for LIGHT_ARMOR → role_bonus stacks on top.
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role,
            gear_archetype=GearArchetype.LIGHT_ARMOR,
        )

        self._equip_armor(char, base_soak=3)

        raw_damage = 20
        result = apply_equipped_armor_soak(char, raw_damage)

        # compat_physical = 3 (LIGHT_ARMOR is compatible), incompat_physical = 0.
        # resonant = equipment_walk_total_unblended = covenant_role_base_total = 4 (level=2, bpl=2).
        # soak = 3 + max(0, 4) = 7. Post-soak damage = max(0, 20 - 7) = 13.
        self.assertEqual(result, 13)

    def test_covenant_soak_takes_less_damage_than_non_covenant(self) -> None:
        """Covenant member takes less damage than a non-member with the same armor."""
        armor_soak_target = wire_armor_soak_modifier_target()

        # Non-covenant character.
        char_nc = CharacterFactory(db_key="NoCovSoakChar")
        sheet_nc = CharacterSheetFactory(character=char_nc, primary_persona=False)  # noqa: F841
        self._equip_armor(char_nc, base_soak=3, name="NoCovArmor")
        no_cov_result = apply_equipped_armor_soak(char_nc, 20)
        # No role → resonant pool = 0; incompat_physical = 3 (no engaged role, armor is
        # incompatible); compat_physical = 0. soak = 0 + max(3, 0) = 3; damage = 17.
        self.assertEqual(no_cov_result, 17)

        # Covenant character with same armor and an engaged role.
        char_c = CharacterFactory(db_key="CovSoakChar2")
        sheet_c = CharacterSheetFactory(character=char_c, primary_persona=False)
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=sheet_c, character_class=char_class, level=2)
        sheet_c.invalidate_class_level_cache()

        membership = make_engaged_member(character_sheet=sheet_c)
        char_c.covenant_roles.invalidate()

        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role,
            modifier_target=armor_soak_target,
            bonus_per_level=2,
        )
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role,
            gear_archetype=GearArchetype.LIGHT_ARMOR,
        )
        self._equip_armor(char_c, base_soak=3, name="CovArmor")

        cov_result = apply_equipped_armor_soak(char_c, 20)
        # covenant bonus = 4 → total soak = 7 → damage = 13. Less than non-cov (17).
        self.assertLess(cov_result, no_cov_result)
        self.assertEqual(cov_result, 13)


class NonCovenantRegressionGuardTests(TestCase):
    """(c) Non-covenant regression guard: no engaged role → bonus 0, base unchanged."""

    def test_no_engaged_role_modifier_total_equals_zero_for_unseeded(self) -> None:
        """With no engaged role and no target seeded, modifier total is 0."""
        char = CharacterFactory(db_key="NoRoleNoSeedChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)

        # No covenant role, no seeded weapon_damage target → _combat_target_bonus = 0.
        result = _combat_target_bonus(sheet, WEAPON_DAMAGE_TARGET_NAME)
        self.assertEqual(result, 0)

    def test_no_engaged_role_soak_reduces_by_armor_only(self) -> None:
        """With no engaged covenant role, apply_equipped_armor_soak uses armor soak only.

        Non-covenant: resonant pool = 0 (equipment_walk_total_unblended = 0; no role/facets).
        All armor falls in the incompatible bucket (no engaged role → no compatibility match).
        soak = compat_physical(0) + max(incompat_physical, resonant=0) = armor only.
        """
        char = CharacterFactory(db_key="NoRoleSoakChar")
        sheet_nc = CharacterSheetFactory(character=char, primary_persona=False)  # noqa: F841

        wire_armor_soak_modifier_target()  # seed the target row but no covenant role

        template = ItemTemplateFactory(
            gear_archetype=GearArchetype.LIGHT_ARMOR,
            base_armor_soak=4,
            max_durability=30,
            name="NoRoleSoakArmor",
        )
        inst = ItemInstanceFactory(template=template, durability=30)
        EquippedItemFactory(
            character=char,
            item_instance=inst,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        char.equipped_items.invalidate()

        result = apply_equipped_armor_soak(char, 20)
        # No covenant role → resonant pool = 0; armor falls in incompat bucket.
        # soak = 0 + max(incompat_physical=4, resonant=0) = 4. Damage = max(0, 20 - 4) = 16.
        self.assertEqual(result, 16)


class UnseededTargetGuardTests(TestCase):
    """(d) Unseeded-target guard: _combat_target_bonus returns 0 when target row is absent."""

    def test_combat_target_bonus_returns_zero_when_target_not_seeded(self) -> None:
        """With no ModifierTarget named WEAPON_DAMAGE_TARGET_NAME seeded, returns 0 safely."""
        char = CharacterFactory(db_key="UnseededTargetChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)

        # No wire_weapon_damage_modifier_target() call → DoesNotExist → 0.
        result = _combat_target_bonus(sheet, WEAPON_DAMAGE_TARGET_NAME)
        self.assertEqual(result, 0)

    def test_combat_target_bonus_with_seeded_target_and_no_role_equals_zero(self) -> None:
        """With a seeded ModifierTarget but no covenant role → bonus = 0.

        Seeding the target and equipping a weapon makes covenant_role_bonus run, but
        with no engaged roles it exits early and returns 0. So _combat_target_bonus = 0
        (no eager modifiers, equipment_walk = 0 since no engaged roles).
        """
        char = CharacterFactory(db_key="SeededNoRoleChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)

        wire_weapon_damage_modifier_target()  # seed the target

        template = ItemTemplateFactory(
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
            base_weapon_damage=5,
            max_durability=10,
            name="SeededNoRoleWeapon",
        )
        item = ItemInstanceFactory(template=template, durability=10)
        EquippedItemFactory(
            character=char,
            item_instance=item,
            body_region=BodyRegion.RIGHT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        char.equipped_items.invalidate()

        result = _combat_target_bonus(sheet, WEAPON_DAMAGE_TARGET_NAME)
        # No covenant role → covenant_role_bonus early exits → equipment_walk_total = 0.
        # No eager modifiers. get_modifier_total = 0.
        self.assertEqual(result, 0)
