from django.test import TestCase

from world.covenants.factories import CovenantRoleBonusFactory, CovenantRoleFactory
from world.covenants.models import CovenantRoleBonus
from world.mechanics.factories import ModifierTargetFactory


class CovenantRoleBonusModelTests(TestCase):
    def test_unique_role_target(self) -> None:
        role = CovenantRoleFactory()
        target = ModifierTargetFactory(name="RoleBonusTarget")
        CovenantRoleBonus.objects.create(
            covenant_role=role, modifier_target=target, bonus_per_level=2
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            CovenantRoleBonus.objects.create(
                covenant_role=role, modifier_target=target, bonus_per_level=3
            )

    def test_factory_builds(self) -> None:
        config = CovenantRoleBonusFactory(bonus_per_level=4)
        self.assertEqual(config.bonus_per_level, 4)
        self.assertIn(str(config.bonus_per_level), str(config))


class RoleBaseBonusForTargetTests(TestCase):
    def test_returns_level_times_coefficient(self) -> None:
        from world.mechanics.services import role_base_bonus_for_target

        config = CovenantRoleBonusFactory(bonus_per_level=3)
        self.assertEqual(
            role_base_bonus_for_target(
                config.covenant_role, config.modifier_target, character_level=4
            ),
            12,
        )

    def test_returns_zero_when_no_row(self) -> None:
        from world.mechanics.services import role_base_bonus_for_target

        role = CovenantRoleFactory()
        target = ModifierTargetFactory(name="NoRoleBonusTarget")
        self.assertEqual(role_base_bonus_for_target(role, target, character_level=9), 0)
