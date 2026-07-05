"""Tests for CompanionDeployment model (#1873)."""

from django.test import TestCase

from world.battles.factories import BattleFactory, BattleVehicleFactory
from world.companions.factories import CompanionFactory
from world.companions.models import CompanionDeployment


class CompanionDeploymentTests(TestCase):
    def test_deployment_links_companion_battle_vehicle(self):
        companion = CompanionFactory()
        battle = BattleFactory()
        vehicle = BattleVehicleFactory()
        deployment = CompanionDeployment.objects.create(
            companion=companion,
            battle=battle,
            vehicle=vehicle,
        )
        self.assertEqual(deployment.companion, companion)
        self.assertEqual(deployment.battle, battle)
        self.assertEqual(deployment.vehicle, vehicle)

    def test_deployment_str(self):
        companion = CompanionFactory()
        battle = BattleFactory()
        vehicle = BattleVehicleFactory()
        deployment = CompanionDeployment.objects.create(
            companion=companion,
            battle=battle,
            vehicle=vehicle,
        )
        self.assertIn(str(companion.pk), str(deployment))
        self.assertIn(str(battle.pk), str(deployment))

    def test_related_name_on_companion(self):
        companion = CompanionFactory()
        battle = BattleFactory()
        vehicle = BattleVehicleFactory()
        CompanionDeployment.objects.create(
            companion=companion,
            battle=battle,
            vehicle=vehicle,
        )
        self.assertEqual(companion.deployments.count(), 1)

    def test_related_name_on_battle(self):
        companion = CompanionFactory()
        battle = BattleFactory()
        vehicle = BattleVehicleFactory()
        CompanionDeployment.objects.create(
            companion=companion,
            battle=battle,
            vehicle=vehicle,
        )
        self.assertEqual(battle.companion_deployments.count(), 1)

    def test_related_name_on_vehicle(self):
        companion = CompanionFactory()
        battle = BattleFactory()
        vehicle = BattleVehicleFactory()
        CompanionDeployment.objects.create(
            companion=companion,
            battle=battle,
            vehicle=vehicle,
        )
        self.assertEqual(vehicle.companion_deployment.companion, companion)
