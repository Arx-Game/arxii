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
