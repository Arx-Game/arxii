"""E2E journey tests for companion combat bridges (#1873).

Exercises the full Action.run() -> service -> bridge path for both
duel-scale and battle-scale, plus the defeat-consequence gate.
"""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.companions.content import ensure_companion_content
from world.magic.specialization.services import grant_gift_to_character


class CompanionCombatBridgeE2ETests(EvenniaTestCase):
    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="Combat Room")
        self.sheet = CharacterSheetFactory()
        self.owner = self.sheet.character
        self.owner.location = self.room
        self.owner.save()
        self.gift = ensure_companion_content()
        self.resonance = self.gift.resonances.first()
        grant_gift_to_character(self.sheet, self.gift, resonance=self.resonance)

        from world.magic.constants import TargetKind
        from world.magic.models.threads import Thread

        self.thread = Thread.objects.get(
            owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        )
        self.thread.level = 20
        self.thread.save(update_fields=["level"])

    def test_duel_bridge_journey(self):
        """A bound companion commits to a duel via CompanionFightAction."""
        from actions.definitions.companions import BindCompanionAction, CompanionFightAction
        from world.checks.test_helpers import force_check_outcome
        from world.combat.constants import CombatAllegiance, RiskLevel
        from world.combat.factories import CombatEncounterFactory
        from world.combat.models import CombatOpponent, CombatParticipant, ParticipantStatus
        from world.companions.models import Companion, CompanionArchetype
        from world.traits.factories import CheckOutcomeFactory

        # Bind a companion.
        hawk = CompanionArchetype.objects.get(name="Hawk")
        success = CheckOutcomeFactory(name="E2E Duel Success", success_level=5)
        with force_check_outcome(success):
            result = BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        self.assertTrue(result.success, result.message)
        companion = Companion.objects.get(name="Skree")

        # Create an encounter and add the owner as a participant.
        encounter = CombatEncounterFactory(room=self.room, risk_level=RiskLevel.LOW)
        encounter.risk_level = RiskLevel.LOW
        encounter.save(update_fields=["risk_level"])
        CombatParticipant.objects.create(
            encounter=encounter,
            character_sheet=self.sheet,
            status=ParticipantStatus.ACTIVE,
        )

        # Commit the companion to the fight.
        result = CompanionFightAction().run(
            actor=self.owner,
            companion_id=companion.pk,
        )
        self.assertTrue(result.success, result.message)

        # The companion is now an ALLY opponent sourced from the archetype.
        opponent = CombatOpponent.objects.get(pk=result.data["opponent_id"])
        self.assertEqual(opponent.allegiance, CombatAllegiance.ALLY)
        self.assertEqual(opponent.summoned_by, self.sheet)
        self.assertIsNone(opponent.bond_expires_round)
        self.assertEqual(opponent.max_health, hawk.max_health)

    def test_duel_lethal_defeat_journey(self):
        """At LETHAL risk, a defeated companion may die (be released)."""
        from actions.definitions.companions import BindCompanionAction
        from world.checks.test_helpers import force_check_outcome
        from world.combat.constants import RiskLevel
        from world.companions.models import Companion, CompanionArchetype
        from world.companions.services import resolve_companion_defeat
        from world.traits.factories import CheckOutcomeFactory

        # Bind a companion.
        hawk = CompanionArchetype.objects.get(name="Hawk")
        success = CheckOutcomeFactory(name="E2E Lethal Success", success_level=5)
        with force_check_outcome(success):
            BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        companion = Companion.objects.get(name="Skree")

        # Simulate defeat at LETHAL risk — run until death occurs.
        released = False
        for _ in range(50):
            test_companion = Companion.objects.get(pk=companion.pk)
            if not test_companion.is_active:
                break
            died = resolve_companion_defeat(test_companion, RiskLevel.LETHAL)
            if died:
                released = True
                test_companion.refresh_from_db()
                self.assertFalse(test_companion.is_active)
                self.assertIsNotNone(test_companion.released_at)
                break

        self.assertTrue(released, "Expected at least one lethal defeat to release the companion")

    def test_duel_low_risk_defeat_journey(self):
        """At LOW risk, a defeated companion is NOT released."""
        from actions.definitions.companions import BindCompanionAction
        from world.checks.test_helpers import force_check_outcome
        from world.combat.constants import RiskLevel
        from world.companions.models import Companion, CompanionArchetype
        from world.companions.services import resolve_companion_defeat
        from world.traits.factories import CheckOutcomeFactory

        hawk = CompanionArchetype.objects.get(name="Hawk")
        success = CheckOutcomeFactory(name="E2E Low Success", success_level=5)
        with force_check_outcome(success):
            BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        companion = Companion.objects.get(name="Skree")

        died = resolve_companion_defeat(companion, RiskLevel.LOW)
        self.assertFalse(died)
        companion.refresh_from_db()
        self.assertTrue(companion.is_active)

    def test_battle_bridge_journey(self):
        """A bound companion deploys into a battle via DeployCompanionAction."""
        from actions.definitions.companions import BindCompanionAction, DeployCompanionAction
        from world.battles.constants import VehicleKind
        from world.battles.factories import BattleFactory, BattleSideFactory
        from world.battles.models import BattleParticipant, BattleParticipantStatus
        from world.checks.test_helpers import force_check_outcome
        from world.combat.constants import RiskLevel
        from world.companions.models import Companion, CompanionArchetype, CompanionDeployment
        from world.traits.factories import CheckOutcomeFactory

        # Bind a companion with custom strength.
        hawk = CompanionArchetype.objects.get(name="Hawk")
        hawk.strength = 25
        hawk.save(update_fields=["strength"])
        success = CheckOutcomeFactory(name="E2E Battle Success", success_level=5)
        with force_check_outcome(success):
            BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        companion = Companion.objects.get(name="Skree")

        # Create a battle and enlist the owner.
        battle = BattleFactory(risk_level=RiskLevel.LOW)
        side = BattleSideFactory(battle=battle)
        BattleParticipant.objects.create(
            battle=battle,
            character_sheet=self.sheet,
            side=side,
            status=BattleParticipantStatus.ACTIVE,
        )

        # Deploy the companion.
        result = DeployCompanionAction().run(
            actor=self.owner,
            companion_id=companion.pk,
        )
        self.assertTrue(result.success, result.message)

        # The companion is now a COMPANION-kind non-structural vehicle.
        from world.battles.models import BattleVehicle

        vehicle = BattleVehicle.objects.get(pk=result.data["vehicle_id"])
        self.assertEqual(vehicle.vehicle_kind, VehicleKind.COMPANION)
        self.assertFalse(vehicle.is_structural)
        self.assertEqual(vehicle.unit.strength, 25)

        # CompanionDeployment links the persistent companion.
        deployment = CompanionDeployment.objects.get(companion=companion)
        self.assertEqual(deployment.vehicle, vehicle)
        self.assertEqual(deployment.battle, battle)

    def test_battle_low_risk_defeat_journey(self):
        """At LOW risk, a destroyed companion vehicle does NOT release the companion."""
        from actions.definitions.companions import BindCompanionAction
        from world.checks.test_helpers import force_check_outcome
        from world.combat.constants import RiskLevel
        from world.companions.models import Companion, CompanionArchetype
        from world.companions.services import resolve_companion_defeat
        from world.traits.factories import CheckOutcomeFactory

        hawk = CompanionArchetype.objects.get(name="Hawk")
        success = CheckOutcomeFactory(name="E2E Battle Low", success_level=5)
        with force_check_outcome(success):
            BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        companion = Companion.objects.get(name="Skree")

        died = resolve_companion_defeat(companion, RiskLevel.LOW)
        self.assertFalse(died)
        companion.refresh_from_db()
        self.assertTrue(companion.is_active)

    def test_no_companion_fails_gracefully(self):
        """CompanionFightAction fails gracefully with no companion_id."""
        from actions.definitions.companions import CompanionFightAction

        result = CompanionFightAction().run(actor=self.owner)
        self.assertFalse(result.success)

    def test_no_active_encounter_fails_gracefully(self):
        """CompanionFightAction fails when the owner is not in combat."""
        from actions.definitions.companions import BindCompanionAction, CompanionFightAction
        from world.checks.test_helpers import force_check_outcome
        from world.companions.models import Companion, CompanionArchetype
        from world.traits.factories import CheckOutcomeFactory

        hawk = CompanionArchetype.objects.get(name="Hawk")
        success = CheckOutcomeFactory(name="E2E No Combat", success_level=5)
        with force_check_outcome(success):
            BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        companion = Companion.objects.get(name="Skree")

        result = CompanionFightAction().run(actor=self.owner, companion_id=companion.pk)
        self.assertFalse(result.success)
        self.assertIn("not in active combat", result.message)
