"""Tests for the order_companion service (#1921)."""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.create import create_object

from actions.constants import ActionCategory
from typeclasses.companions import CompanionObject
from world.combat.constants import CombatAllegiance, OpponentStatus, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
from world.combat.models import CombatOpponent, CombatParticipant
from world.companions.constants import (
    CompanionAbilityKind,
    CompanionOrderKind,
)
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.companions.models import CompanionAbility, CompanionOrder
from world.companions.services import (
    CompanionOrderError,
    materialize_companion_as_combat_opponent,
    order_companion,
)


def _bind_with_object(companion):
    """Give a companion a live CompanionObject so it can be materialized."""
    obj = create_object(CompanionObject, key=companion.name, nohome=True)
    companion.objectdb = obj
    companion.save(update_fields=["objectdb"])
    return companion


class OrderCompanionDuelTests(TestCase):
    """Duel-scale ordering via encounter."""

    def setUp(self):
        self.archetype = CompanionArchetypeFactory(name="TestBeastOrder")
        self.companion = _bind_with_object(CompanionFactory(archetype=self.archetype))
        self.encounter = CombatEncounterFactory()
        self.threat_pool = ThreatPoolFactory()
        self.participant = CombatParticipant.objects.create(
            character_sheet=self.companion.owner,
            encounter=self.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        self.encounter.round_number = 1
        self.encounter.save(update_fields=["round_number"])

        # Materialize the companion into the encounter as an ALLY opponent
        self.ally_opponent = materialize_companion_as_combat_opponent(
            self.companion,
            self.encounter,
            threat_pool=self.threat_pool,
        )

        # Add an enemy opponent
        self.enemy = CombatOpponent.objects.create(
            encounter=self.encounter,
            name="Goblin",
            tier="mook",
            health=20,
            max_health=20,
            soak_value=0,
            threat_pool=self.threat_pool,
            allegiance=CombatAllegiance.ENEMY,
            status=OpponentStatus.ACTIVE,
        )

    def test_hold_order_creates(self):
        order = order_companion(
            companion=self.companion,
            order_kind=CompanionOrderKind.HOLD,
            encounter=self.encounter,
            round_number=1,
        )
        self.assertEqual(order.order_kind, CompanionOrderKind.HOLD)
        self.assertEqual(order.encounter, self.encounter)

    def test_attack_target_sets_target(self):
        order = order_companion(
            companion=self.companion,
            order_kind=CompanionOrderKind.ATTACK_TARGET,
            encounter=self.encounter,
            round_number=1,
            target_opponent=self.enemy,
        )
        self.assertEqual(order.target_opponent, self.enemy)

    def test_defend_ally_sets_participant(self):
        order = order_companion(
            companion=self.companion,
            order_kind=CompanionOrderKind.DEFEND_ALLY,
            encounter=self.encounter,
            round_number=1,
            defending_participant=self.participant,
        )
        self.assertEqual(order.defending_participant, self.participant)

    def test_order_upserts_same_round(self):
        order_companion(
            companion=self.companion,
            order_kind=CompanionOrderKind.HOLD,
            encounter=self.encounter,
            round_number=1,
        )
        order_companion(
            companion=self.companion,
            order_kind=CompanionOrderKind.ATTACK_TARGET,
            encounter=self.encounter,
            round_number=1,
            target_opponent=self.enemy,
        )
        self.assertEqual(CompanionOrder.objects.filter(companion=self.companion).count(), 1)
        order = CompanionOrder.objects.get(companion=self.companion)
        self.assertEqual(order.order_kind, CompanionOrderKind.ATTACK_TARGET)

    def test_attack_target_without_target_raises(self):
        with self.assertRaises(CompanionOrderError):
            order_companion(
                companion=self.companion,
                order_kind=CompanionOrderKind.ATTACK_TARGET,
                encounter=self.encounter,
                round_number=1,
            )

    def test_attack_target_wrong_allegiance_raises(self):
        ally_target = CombatOpponent.objects.create(
            encounter=self.encounter,
            name="Other Ally",
            tier="mook",
            health=20,
            max_health=20,
            allegiance=CombatAllegiance.ALLY,
            status=OpponentStatus.ACTIVE,
        )
        with self.assertRaises(CompanionOrderError):
            order_companion(
                companion=self.companion,
                order_kind=CompanionOrderKind.ATTACK_TARGET,
                encounter=self.encounter,
                round_number=1,
                target_opponent=ally_target,
            )

    def test_not_deployed_raises(self):
        other_companion = _bind_with_object(CompanionFactory(archetype=self.archetype))
        with self.assertRaises(CompanionOrderError):
            order_companion(
                companion=other_companion,
                order_kind=CompanionOrderKind.HOLD,
                encounter=self.encounter,
                round_number=1,
            )

    def test_ability_wrong_archetype_raises(self):
        other_archetype = CompanionArchetypeFactory(name="OtherArchetype")
        ability = CompanionAbility.objects.create(
            archetype=other_archetype,
            name="OtherRend",
            ability_kind=CompanionAbilityKind.ATTACK,
            attack_category=ActionCategory.PHYSICAL,
        )
        with self.assertRaises(CompanionOrderError):
            order_companion(
                companion=self.companion,
                order_kind=CompanionOrderKind.HOLD,
                encounter=self.encounter,
                round_number=1,
                ability=ability,
            )

    def test_no_encounter_or_battle_raises(self):
        with self.assertRaises(CompanionOrderError):
            order_companion(
                companion=self.companion,
                order_kind=CompanionOrderKind.HOLD,
                round_number=1,
            )


class OrderCompanionBattleTests(TestCase):
    """Battle-scale ordering via battle."""

    def setUp(self):
        from world.battles.constants import VehicleKind
        from world.battles.factories import BattleFactory, BattleSideFactory
        from world.battles.services import create_battle_vehicle
        from world.companions.models import CompanionDeployment

        self.companion = _bind_with_object(CompanionFactory())
        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle)
        self.vehicle = create_battle_vehicle(
            battle=self.battle,
            side=self.side,
            place_name=self.companion.name,
            vehicle_kind=VehicleKind.COMPANION,
            is_structural=False,
        )
        self.deployment = CompanionDeployment.objects.create(
            companion=self.companion,
            battle=self.battle,
            vehicle=self.vehicle,
        )

    def test_battle_attack_target_creates_order(self):
        from world.battles.factories import BattleUnitFactory

        target_unit = BattleUnitFactory(battle=self.battle, side=self.battle.sides.first())
        order = order_companion(
            companion=self.companion,
            order_kind=CompanionOrderKind.ATTACK_TARGET,
            battle=self.battle,
            round_number=1,
            target_unit=target_unit,
        )
        self.assertEqual(order.order_kind, CompanionOrderKind.ATTACK_TARGET)
        self.assertEqual(order.battle, self.battle)

    def test_battle_hold_creates_order(self):
        order = order_companion(
            companion=self.companion,
            order_kind=CompanionOrderKind.HOLD,
            battle=self.battle,
            round_number=1,
        )
        self.assertEqual(order.order_kind, CompanionOrderKind.HOLD)

    def test_battle_not_deployed_raises(self):
        other_companion = _bind_with_object(CompanionFactory())
        with self.assertRaises(CompanionOrderError):
            order_companion(
                companion=other_companion,
                order_kind=CompanionOrderKind.HOLD,
                battle=self.battle,
                round_number=1,
            )
