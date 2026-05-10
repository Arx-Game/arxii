"""Engagement gating + cross-type stacking for covenant_role_bonus.

Spec 2026-05-09 §3.6 — covenant role bonuses fire only for engaged
memberships and stack additively across covenant types.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    GearArchetypeCompatibilityFactory,
    make_engaged_member,
)
from world.covenants.services import set_engaged_membership
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import (
    EquippedItemFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
    TemplateSlotFactory,
)
from world.magic.factories import ResonanceFactory
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.services import covenant_role_bonus


class CovenantRoleBonusGatingTests(TestCase):
    """Gating and stacking behaviour for covenant_role_bonus (Spec D §5.6, §3.6 engagement)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="GatingTestChar")
        cls.sheet = CharacterSheetFactory(character=cls.character, primary_persona=False)

        # Resonance category target (per existing tests' shape)
        cls.resonance = ResonanceFactory()
        cls.resonance_category = ModifierCategoryFactory(name="resonance_gating")
        cls.target = ModifierTargetFactory(
            name="GatingTarget",
            category=cls.resonance_category,
            target_resonance=cls.resonance,
        )

        # Equipped item template + instance + slot + equipped row
        cls.quality_tier = QualityTierFactory(name="GatingQT", stat_multiplier=Decimal("1.00"))
        cls.template = ItemTemplateFactory(
            facet_capacity=1, gear_archetype=GearArchetype.HEAVY_ARMOR
        )
        TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.instance = ItemInstanceFactory(template=cls.template, quality_tier=cls.quality_tier)
        EquippedItemFactory(
            character=cls.character,
            item_instance=cls.instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

    def setUp(self) -> None:
        # Ensure handler caches are fresh before each test so per-test CCR
        # rows created in setUpTestData and within tests don't bleed.
        self.character.covenant_roles.invalidate()
        self.character.equipped_items.invalidate()

    def test_returns_zero_when_no_engagement(self) -> None:
        """Active membership but engaged=False → no role bonus.

        Spec §3.6: engagement is required for role bonuses to fire. A membership
        row that exists but has engaged=False must contribute nothing.
        """
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=CovenantRoleFactory(covenant_type=CovenantType.DURANCE),
            # engaged defaults to False in the factory
        )
        self.character.covenant_roles.invalidate()
        # role_base_bonus_for_target is a placeholder returning 0; the function
        # must return 0 because no engaged roles exist — early exit before the loop.
        self.assertEqual(covenant_role_bonus(self.sheet, self.target), 0)

    def test_returns_zero_when_no_roles_at_all(self) -> None:
        """No CCR rows at all → returns 0 without error."""
        # No rows created for this character in this test (setUp invalidated cache)
        result = covenant_role_bonus(self.sheet, self.target)
        self.assertEqual(result, 0)

    def test_returns_engaged_role_bonus(self) -> None:
        """Single engaged Durance membership → loop fires for that role.

        With placeholder role_base_bonus and item_mundane_stat both 0, and
        compatible gear, total += 0 + 0 = 0. The load-bearing assertion is
        that the function runs without error and returns an int.
        """
        membership = make_engaged_member(character_sheet=self.sheet)
        GearArchetypeCompatibilityFactory(
            covenant_role=membership.covenant_role,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )
        self.character.covenant_roles.invalidate()
        result = covenant_role_bonus(self.sheet, self.target)
        self.assertIsInstance(result, int)
        self.assertEqual(result, 0)

    def test_stacks_durance_and_battle(self) -> None:
        """Engaged Durance + engaged Battle → both roles appear in the handler.

        The function must iterate both engaged roles and sum contributions.
        With placeholder bonus functions returning 0, the observable difference
        is that currently_engaged_roles() returns both roles, and the function
        runs without error.
        """
        durance_m = make_engaged_member(character_sheet=self.sheet)
        battle_cov = CovenantFactory(covenant_type=CovenantType.BATTLE)
        battle_role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        battle_m = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=battle_cov,
            covenant_role=battle_role,
        )
        set_engaged_membership(membership=battle_m)
        self.character.covenant_roles.invalidate()

        # Both engaged roles must be returned by the handler
        engaged = self.character.covenant_roles.currently_engaged_roles()
        self.assertIn(durance_m.covenant_role, engaged)
        self.assertIn(battle_role, engaged)

        # Function iterates both roles — runs without error
        result = covenant_role_bonus(self.sheet, self.target)
        self.assertIsInstance(result, int)

    def test_non_engaged_role_excluded_when_engaged_exists(self) -> None:
        """An active-but-not-engaged row does not double-count when an engaged row also exists.

        Create two active Durance memberships: one engaged, one not. Only the
        engaged one must influence currently_engaged_roles(). The non-engaged
        row must be invisible to the function.
        """
        engaged_m = make_engaged_member(character_sheet=self.sheet)
        # Second Durance covenant (different covenant, same type) — not engaged
        second_cov = CovenantFactory(covenant_type=CovenantType.DURANCE)
        second_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=second_cov,
            covenant_role=second_role,
            # engaged defaults to False
        )
        self.character.covenant_roles.invalidate()

        engaged = self.character.covenant_roles.currently_engaged_roles()
        self.assertIn(engaged_m.covenant_role, engaged)
        self.assertNotIn(second_role, engaged)

        result = covenant_role_bonus(self.sheet, self.target)
        self.assertIsInstance(result, int)
