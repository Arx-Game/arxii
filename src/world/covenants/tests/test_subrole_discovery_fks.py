from django.core.exceptions import ValidationError
from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.covenants.factories import (
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)


class SubroleDiscoveryFKTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.primary = CovenantRoleFactory()

    def test_primary_role_rejects_discovery_achievement(self):
        self.primary.discovery_achievement = AchievementFactory()
        with self.assertRaises(ValidationError):
            self.primary.full_clean()

    def test_subrole_accepts_discovery_achievement(self):
        sub = SubroleCovenantRoleFactory(parent_role=self.primary)
        sub.discovery_achievement = AchievementFactory()
        sub.full_clean()  # must not raise
