"""Tests for CompanionDeployment model (#1873)."""

from django.test import TestCase
from django.utils import timezone

from world.battles.constants import BattleOutcome, BattleUnitStatus
from world.battles.factories import BattleFactory, BattleVehicleFactory
from world.battles.services import conclude_battle
from world.combat.constants import RiskLevel
from world.companions.battle_wiring import apply_companion_battle_outcome
from world.companions.factories import CompanionFactory
from world.companions.factories_combat import COMPANION_DIE_LABEL, create_companion_defeat_pool
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


def _force_draw(pool, label: str) -> None:
    """Zero every other consequence's weight so *label* is always drawn.

    Copied from test_defeat_consequences.py's helper: ConsequencePoolEntry.Meta
    has no ordering, so a cumulative-weight boundary computed from iteration
    order is not guaranteed (it would pass on SQLite and could flake on
    Postgres). Call this before anything reads pool.cached_consequences - it is
    a cached_property, so once computed it will not reflect these overrides.
    """
    from actions.models import ConsequencePoolEntry

    entries = ConsequencePoolEntry.objects.filter(pool=pool).select_related("consequence")
    for entry in entries:
        if entry.consequence.label != label:
            entry.weight_override = 0
            entry.save(update_fields=["weight_override"])


class ApplyCompanionBattleOutcomeTests(TestCase):
    """Task 7 (#3652): the battle-scale twin of the duel-scale defeat hook."""

    def setUp(self) -> None:
        self.pool = create_companion_defeat_pool()
        _force_draw(self.pool, COMPANION_DIE_LABEL)

    def _deploy(self, *, battle, status: str, is_structural: bool = False) -> CompanionDeployment:
        companion = CompanionFactory()
        vehicle = BattleVehicleFactory(
            unit__battle=battle,
            unit__status=status,
            is_structural=is_structural,
        )
        return CompanionDeployment.objects.create(
            companion=companion,
            battle=battle,
            vehicle=vehicle,
        )

    def test_lethal_destroyed_vehicle_releases_companion(self):
        battle = BattleFactory(risk_level=RiskLevel.LETHAL)
        deployment = self._deploy(battle=battle, status=BattleUnitStatus.DESTROYED)

        apply_companion_battle_outcome(battle)

        deployment.companion.refresh_from_db()
        self.assertFalse(deployment.companion.is_active)
        self.assertIsNotNone(deployment.companion.released_at)

    def test_low_risk_destroyed_vehicle_leaves_companion_untouched(self):
        battle = BattleFactory(risk_level=RiskLevel.LOW)
        deployment = self._deploy(battle=battle, status=BattleUnitStatus.DESTROYED)

        apply_companion_battle_outcome(battle)

        deployment.companion.refresh_from_db()
        self.assertTrue(deployment.companion.is_active)
        self.assertIsNone(deployment.companion.released_at)

    def test_active_vehicle_leaves_companion_untouched_at_lethal(self):
        battle = BattleFactory(risk_level=RiskLevel.LETHAL)
        deployment = self._deploy(battle=battle, status=BattleUnitStatus.ACTIVE)

        apply_companion_battle_outcome(battle)

        deployment.companion.refresh_from_db()
        self.assertTrue(deployment.companion.is_active)
        self.assertIsNone(deployment.companion.released_at)

    def test_already_released_companion_is_skipped(self):
        battle = BattleFactory(risk_level=RiskLevel.LETHAL)
        deployment = self._deploy(battle=battle, status=BattleUnitStatus.DESTROYED)
        companion = deployment.companion
        companion.released_at = timezone.now()
        companion.save(update_fields=["released_at"])

        # Should not raise even though the companion's objectdb is already gone.
        apply_companion_battle_outcome(battle)

        companion.refresh_from_db()
        self.assertIsNotNone(companion.released_at)

    def test_conclude_battle_is_idempotent_against_the_hook(self):
        battle = BattleFactory(risk_level=RiskLevel.LETHAL)
        deployment = self._deploy(battle=battle, status=BattleUnitStatus.DESTROYED)

        conclude_battle(battle=battle, outcome=BattleOutcome.ATTACKER_DECISIVE)
        deployment.companion.refresh_from_db()
        self.assertFalse(deployment.companion.is_active)
        first_release = deployment.companion.released_at

        # conclude_battle no-ops once already concluded, so the hook does not
        # re-run and there is nothing left to double-resolve.
        conclude_battle(battle=battle, outcome=BattleOutcome.ATTACKER_DECISIVE)
        deployment.companion.refresh_from_db()
        self.assertEqual(deployment.companion.released_at, first_release)
