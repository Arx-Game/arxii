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
from world.combat.services import _resonant_armor_soak, apply_equipped_armor_soak
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleBonusFactory,
    CovenantRoleDefenseProfileFactory,
    CovenantRoleFactory,
    GearArchetypeCompatibilityFactory,
    SubroleCovenantRoleFactory,
    make_engaged_member,
)
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory
from world.magic.models import Thread


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
        self.assertEqual(apply_equipped_armor_soak(char, 20), 10)

    def test_incompatible_high_level_resonant_wins(self) -> None:
        """Level 3 incompatible heavy armor: resonant battle-lingerie beats platemail.

        resonant = 3 * 4 = 12; physical (incompatible) = 10. soak = max(10, 12) = 12.
        damage 20 -> 8.
        """
        char, _, _ = self._covenant_char(level=3, bonus_per_level=4, db_key="HighLvlIncompat")
        self._equip(char, GearArchetype.HEAVY_ARMOR, 10, "HighPlate")
        self.assertEqual(apply_equipped_armor_soak(char, 20), 8)

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
        self.assertEqual(apply_equipped_armor_soak(char, 20), 13)

    def test_non_covenant_armor_only(self) -> None:
        """No engaged role: resonant = 0; soak = max(physical, 0) = physical."""
        char = CharacterFactory(db_key="NonCovGate")
        CharacterSheetFactory(character=char, primary_persona=False)
        wire_armor_soak_modifier_target()
        self._equip(char, GearArchetype.LIGHT_ARMOR, 4, "NonCovArmor")
        self.assertEqual(apply_equipped_armor_soak(char, 20), 16)

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


class DefenseProfileGearSubstitutionTests(TestCase):
    """Defense-profile gear-substitution fraction at the armor-soak seam (#2533).

    ``apply_equipped_armor_soak`` scales COMPATIBLE soak by
    ``gear_additive_fraction(character)`` before the compatible-additive /
    incompatible-max blend. No engaged role has a profile → fraction 1 (legacy,
    byte-identical — proven by ``ArmorSoakRoleGateTests`` passing unmodified).
    """

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

    def _engaged_subrole_char(
        self, *, subrole_tenths: int | None, parent_tenths: int | None, level=2, bonus_per_level=2
    ):
        """Engaged-membership on the ANCHOR (parent) role, resolved to the sub-role.

        Mirrors the proven order from
        ``test_vow_scaling.CovenantRoleActionScalingTests
        .test_sub_role_scaling_resolves_via_parent_row``: the COVENANT_ROLE thread
        must exist BEFORE ``set_engaged_membership`` runs, because engaging warms
        (and thus freezes) the character's ``threads`` handler cache as a side
        effect (``_invalidate_role_caches`` invalidates it, then the very next line
        reads it back via ``passive_capability_grants()``) — engaging first would
        cache an empty thread list and the sub-role would never resolve.
        """
        from world.covenants.factories import CharacterCovenantRoleFactory
        from world.covenants.services import set_engaged_membership

        char = CharacterFactory(db_key="SubRoleFractionChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=char, character_class=char_class, level=level)
        sheet.invalidate_class_level_cache()
        target = wire_armor_soak_modifier_target()

        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        parent = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        resonance = ResonanceFactory()
        subrole = SubroleCovenantRoleFactory(
            parent_role=parent, resonance=resonance, unlock_thread_level=3
        )
        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=covenant, covenant_role=parent
        )

        # engaged_roles resolve to the sub-role, so both the resonant-pool lookup
        # (covenant_role_base_total -> role_base_bonus_for_target) and gear
        # compatibility key on the sub-role, not the parent.
        CovenantRoleBonusFactory(
            covenant_role=subrole, modifier_target=target, bonus_per_level=bonus_per_level
        )
        GearArchetypeCompatibilityFactory(
            covenant_role=subrole, gear_archetype=GearArchetype.LIGHT_ARMOR
        )
        Thread.objects.create(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent,
            resonance=resonance,
            level=10,
        )

        if parent_tenths is not None:
            CovenantRoleDefenseProfileFactory(
                covenant_role=parent, gear_additive_tenths=parent_tenths
            )
        if subrole_tenths is not None:
            CovenantRoleDefenseProfileFactory(
                covenant_role=subrole, gear_additive_tenths=subrole_tenths
            )

        set_engaged_membership(membership=membership)
        char.covenant_roles.invalidate()

        # Sanity: the engaged role resolves to the sub-role, not the parent.
        self.assertEqual(char.covenant_roles.currently_engaged_roles(), [subrole])

        return char, sheet, membership

    def test_defense_profile_fraction_scales_compatible_soak(self) -> None:
        """A gear_additive_tenths=3 profile scales COMPATIBLE soak by 0.3; resonant and
        the incompatible-max side are unaffected (#2533).

        compat_physical = 10 (LIGHT_ARMOR, compatible) -> scaled = int(10 * 0.3) = 3.
        resonant = 2 * 2 = 4 (unaffected by the profile). soak = 3 + max(0, 4) = 7.
        damage 20 -> 13.
        """
        char, _, membership = self._covenant_char(level=2, bonus_per_level=2, db_key="FractionChar")
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role, gear_archetype=GearArchetype.LIGHT_ARMOR
        )
        CovenantRoleDefenseProfileFactory(
            covenant_role=membership.covenant_role, gear_additive_tenths=3
        )
        self._equip(char, GearArchetype.LIGHT_ARMOR, 10, "FractionArmor")

        self.assertEqual(_resonant_armor_soak(char), 4)
        self.assertEqual(apply_equipped_armor_soak(char, 20), 13)

    def test_multi_role_defense_profile_max_governs(self) -> None:
        """Two engaged roles each with a defense profile: the higher fraction governs.

        role_a (DURANCE) profile=9 tenths, role_b (BATTLE) profile=2 tenths — role_b
        need not even be gear-compatible: the fraction is a per-character MAX over
        every engaged role's profile, not scoped to the compatibility-granting role.
        compat_physical = 10 (compatible via role_a) -> scaled = int(10 * 0.9) = 9.
        resonant = 2 * 2 = 4 (role_a's CovenantRoleBonus only). soak = 9 + max(0, 4) = 13.
        damage 20 -> 7.
        """
        char = CharacterFactory(db_key="MultiRoleChar")
        sheet = CharacterSheetFactory(character=char, primary_persona=False)
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=char, character_class=char_class, level=2)
        sheet.invalidate_class_level_cache()
        target = wire_armor_soak_modifier_target()

        covenant_a = CovenantFactory(covenant_type=CovenantType.DURANCE)
        role_a = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        make_engaged_member(character_sheet=sheet, covenant=covenant_a, covenant_role=role_a)
        covenant_b = CovenantFactory(covenant_type=CovenantType.BATTLE)
        role_b = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        make_engaged_member(character_sheet=sheet, covenant=covenant_b, covenant_role=role_b)
        char.covenant_roles.invalidate()

        CovenantRoleBonusFactory(covenant_role=role_a, modifier_target=target, bonus_per_level=2)
        GearArchetypeCompatibilityFactory(
            covenant_role=role_a, gear_archetype=GearArchetype.LIGHT_ARMOR
        )
        CovenantRoleDefenseProfileFactory(covenant_role=role_a, gear_additive_tenths=9)
        CovenantRoleDefenseProfileFactory(covenant_role=role_b, gear_additive_tenths=2)

        self._equip(char, GearArchetype.LIGHT_ARMOR, 10, "MultiRoleArmor")
        self.assertEqual(apply_equipped_armor_soak(char, 20), 7)

    def test_sub_role_profile_replaces_anchor(self) -> None:
        """A sub-role's own defense profile replaces (not blends with) the anchor's.

        parent profile=9 tenths, subrole profile=3 tenths. The resolved engaged role
        is the subrole (thread crossing) -> its own profile (3) governs, not the
        parent's (9). compat_physical = 10 -> scaled = int(10 * 0.3) = 3.
        resonant = 2 * 2 = 4. soak = 3 + 4 = 7. damage 20 -> 13.
        """
        char, _, _ = self._engaged_subrole_char(subrole_tenths=3, parent_tenths=9)
        self._equip(char, GearArchetype.LIGHT_ARMOR, 10, "SubRoleArmor")
        self.assertEqual(apply_equipped_armor_soak(char, 20), 13)

    def test_sub_role_without_profile_uses_anchor(self) -> None:
        """A sub-role with no defense profile of its own falls back to the anchor's.

        parent profile=3 tenths, subrole has none. compat_physical = 10 -> scaled =
        int(10 * 0.3) = 3. resonant = 2 * 2 = 4. soak = 3 + 4 = 7. damage 20 -> 13.
        """
        char, _, _ = self._engaged_subrole_char(subrole_tenths=None, parent_tenths=3)
        self._equip(char, GearArchetype.LIGHT_ARMOR, 10, "SubRoleFallbackArmor")
        self.assertEqual(apply_equipped_armor_soak(char, 20), 13)

    def test_durability_attribution_unchanged_with_profile_fraction(self) -> None:
        """A compatible piece still wears when a profile scales its soak down (#2533).

        Durability wear is keyed on piece-bucket membership (compat_pieces), not on
        the scaled soak's magnitude — unchanged by the #2533 fraction.
        """
        char, _, membership = self._covenant_char(
            level=2, bonus_per_level=2, db_key="FractionWearChar"
        )
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role, gear_archetype=GearArchetype.LIGHT_ARMOR
        )
        CovenantRoleDefenseProfileFactory(
            covenant_role=membership.covenant_role, gear_additive_tenths=3
        )
        inst = self._equip(char, GearArchetype.LIGHT_ARMOR, 10, "FractionWearArmor", durability=30)

        apply_equipped_armor_soak(char, 20)

        inst.refresh_from_db()
        self.assertLess(inst.durability, 30)
