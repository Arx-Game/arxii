"""Tests for companion bridge Actions (#1873)."""

from django.test import TestCase

from actions.definitions.companions import (
    CompanionFightAction,
    DeployCompanionAction,
)
from actions.registry import ACTIONS_BY_KEY
from actions.types import TargetType


class BridgeActionRegistrationTests(TestCase):
    def test_companion_fight_registered(self):
        self.assertIn("companion_fight", ACTIONS_BY_KEY)

    def test_deploy_companion_registered(self):
        self.assertIn("deploy_companion", ACTIONS_BY_KEY)

    def test_actions_target_self(self):
        self.assertEqual(CompanionFightAction().target_type, TargetType.SELF)
        self.assertEqual(DeployCompanionAction().target_type, TargetType.SELF)

    def test_actions_in_companions_category(self):
        self.assertEqual(CompanionFightAction().category, "companions")
        self.assertEqual(DeployCompanionAction().category, "companions")
