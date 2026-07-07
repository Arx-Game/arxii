"""Tests for companion combat bridge services (#1873)."""

from django.test import TestCase

from world.areas.positioning.services import create_position, place_in_position, position_of
from world.battles.constants import VehicleKind
from world.battles.factories import BattleFactory, BattleSideFactory
from world.combat.constants import CombatAllegiance
from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.companions.models import CompanionDeployment
from world.companions.services import (
    materialize_companion_as_battle_vehicle,
    materialize_companion_as_combat_opponent,
)


class MaterializeCompanionAsCombatOpponentTests(TestCase):
    def test_creates_ally_opponent_from_archetype_stats(self):
        archetype = CompanionArchetypeFactory(
            max_health=75,
            soak_value=12,
            tier="elite",
            strength=40,
        )
        companion = CompanionFactory(archetype=archetype)
        # The companion needs a live CompanionObject as its objectdb.
        from evennia.utils.create import create_object

        from typeclasses.companions import CompanionObject

        obj = create_object(
            CompanionObject,
            key=companion.name,
            nohome=True,
        )
        companion.objectdb = obj
        companion.save(update_fields=["objectdb"])

        encounter = CombatEncounterFactory()
        threat_pool = ThreatPoolFactory()

        opponent = materialize_companion_as_combat_opponent(
            companion,
            encounter,
            threat_pool=threat_pool,
        )

        self.assertEqual(opponent.encounter, encounter)
        self.assertEqual(opponent.allegiance, CombatAllegiance.ALLY)
        self.assertEqual(opponent.summoned_by, companion.owner)
        self.assertIsNone(opponent.bond_expires_round)
        self.assertEqual(opponent.max_health, 75)
        self.assertEqual(opponent.soak_value, 12)
        self.assertEqual(opponent.tier, "elite")
        # The companion's objectdb is the opponent's ObjectDB (not ephemeral).
        self.assertEqual(opponent.objectdb, obj)

    def test_defaults_to_owners_current_position(self):
        """Task 3 (#2005): materialization places the companion at the owner's position."""
        from evennia.utils.create import create_object

        from typeclasses.companions import CompanionObject

        archetype = CompanionArchetypeFactory(max_health=75, soak_value=12, tier="elite")
        companion = CompanionFactory(archetype=archetype)

        encounter = CombatEncounterFactory()
        threat_pool = ThreatPoolFactory()

        # Owner's character and the companion's objectdb both live in the encounter room.
        owner_character = companion.owner.character
        owner_character.move_to(encounter.room, quiet=True)
        owner_position = create_position(encounter.room, "owner_pos")
        place_in_position(owner_character, owner_position)

        obj = create_object(CompanionObject, key=companion.name, location=encounter.room)
        companion.objectdb = obj
        companion.save(update_fields=["objectdb"])

        opponent = materialize_companion_as_combat_opponent(
            companion,
            encounter,
            threat_pool=threat_pool,
        )

        self.assertEqual(position_of(opponent.objectdb), owner_position)


class MaterializeCompanionAsBattleVehicleTests(TestCase):
    def test_creates_companion_vehicle_linked_by_deployment(self):
        archetype = CompanionArchetypeFactory(strength=42)
        companion = CompanionFactory(archetype=archetype)
        battle = BattleFactory()
        side = BattleSideFactory(battle=battle)

        vehicle = materialize_companion_as_battle_vehicle(
            companion,
            battle,
            side,
        )

        self.assertEqual(vehicle.vehicle_kind, VehicleKind.COMPANION)
        self.assertFalse(vehicle.is_structural)
        self.assertEqual(vehicle.unit.strength, 42)
        # CompanionDeployment links the persistent companion to the vehicle.
        deployment = CompanionDeployment.objects.get(companion=companion)
        self.assertEqual(deployment.vehicle, vehicle)
        self.assertEqual(deployment.battle, battle)
