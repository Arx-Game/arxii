"""Layer 3 chassis isolation for the mechanics-app covenant-role consumers (#2641):
``vow_stat_scaling_bonus``, ``covenant_role_base_total``, and ``covenant_level_bonus``
never read an engaged SECONDARY membership — zero chassis leak.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleBonusFactory,
    CovenantRoleFactory,
)
from world.covenants.models import CovenantLevelBonus, VowStatScaling
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.services import (
    covenant_level_bonus,
    covenant_role_base_total,
    vow_stat_scaling_bonus,
)


class VowStatScalingChassisIsolationTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character, primary_persona=False)
        category = ModifierCategoryFactory(name="stat_secondary_isolation")
        self.target = ModifierTargetFactory(name="SecondaryIsolationTarget", category=category)

        self.primary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=self.primary_role,
            engaged=True,
            is_secondary=False,
        )
        VowStatScaling.objects.create(
            covenant_role=self.primary_role, modifier_target=self.target, bonus_per_level=3
        )
        resonance = ResonanceFactory()
        ThreadFactory(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_trait=None,
            target_covenant_role=self.primary_role,
            level=4,
        )
        self.character.covenant_roles.invalidate()

    def test_secondary_vow_stat_scaling_never_contributes(self) -> None:
        baseline = vow_stat_scaling_bonus(self.sheet, self.target)
        self.assertEqual(baseline, 12)  # 4 * 3

        secondary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        # A far bigger bonus_per_level — would swamp the result if it leaked.
        VowStatScaling.objects.create(
            covenant_role=secondary_role, modifier_target=self.target, bonus_per_level=100
        )
        secondary_resonance = ResonanceFactory()
        ThreadFactory(
            owner=self.sheet,
            resonance=secondary_resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_trait=None,
            target_covenant_role=secondary_role,
            level=9,
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=secondary_role,
            engaged=True,
            is_secondary=True,
        )
        self.character.covenant_roles.invalidate()

        with_secondary = vow_stat_scaling_bonus(self.sheet, self.target)
        self.assertEqual(with_secondary, baseline)


class CovenantRoleBaseTotalChassisIsolationTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character, primary_persona=False)
        category = ModifierCategoryFactory(name="base_total_secondary_isolation")
        self.target = ModifierTargetFactory(name="BaseTotalIsolationTarget", category=category)

        self.primary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=self.primary_role,
            engaged=True,
            is_secondary=False,
        )
        CovenantRoleBonusFactory(
            covenant_role=self.primary_role, modifier_target=self.target, bonus_per_level=2
        )
        self.character.covenant_roles.invalidate()

    def test_secondary_role_base_total_never_contributes(self) -> None:
        baseline = covenant_role_base_total(self.sheet, self.target)

        secondary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        CovenantRoleBonusFactory(
            covenant_role=secondary_role, modifier_target=self.target, bonus_per_level=1000
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=secondary_role,
            engaged=True,
            is_secondary=True,
        )
        self.character.covenant_roles.invalidate()

        with_secondary = covenant_role_base_total(self.sheet, self.target)
        self.assertEqual(with_secondary, baseline)


class CovenantLevelBonusChassisIsolationTests(TestCase):
    """Conservative primary-only flip (#2641) — see ``covenant_level_bonus``'s
    docstring for why this stays chassis-shaped even though it keys on covenant
    LEVEL, not covenant ROLE."""

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character, primary_persona=False)
        category = ModifierCategoryFactory(name="level_bonus_secondary_isolation")
        self.target = ModifierTargetFactory(name="LevelBonusIsolationTarget", category=category)
        CovenantLevelBonus.objects.create(modifier_target=self.target, bonus_per_level=1)

        self.primary_covenant = CovenantFactory(covenant_type=CovenantType.DURANCE, level=3)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=self.primary_covenant,
            covenant_role=CovenantRoleFactory(covenant_type=CovenantType.DURANCE),
            engaged=True,
            is_secondary=False,
        )
        self.character.covenant_roles.invalidate()

    def test_secondary_covenant_level_never_contributes(self) -> None:
        baseline = covenant_level_bonus(self.sheet, self.target)
        self.assertEqual(baseline, 3)

        # A much higher-level secondary covenant — would swamp the result if it leaked.
        secondary_covenant = CovenantFactory(covenant_type=CovenantType.DURANCE, level=100)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=secondary_covenant,
            covenant_role=CovenantRoleFactory(covenant_type=CovenantType.DURANCE),
            engaged=True,
            is_secondary=True,
        )
        self.character.covenant_roles.invalidate()

        with_secondary = covenant_level_bonus(self.sheet, self.target)
        self.assertEqual(with_secondary, baseline)
