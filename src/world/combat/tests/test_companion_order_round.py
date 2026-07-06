"""Tests for companion order round-tick integration (#1921)."""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.create import create_object

from typeclasses.companions import CompanionObject
from world.combat.constants import CombatAllegiance, OpponentStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponent, CombatParticipant
from world.combat.services import select_npc_actions
from world.companions.constants import CompanionOrderKind
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.companions.services import materialize_companion_as_combat_opponent, order_companion
from world.scenes.constants import RoundStatus


def _bind_with_object(companion):
    """Give a companion a live CompanionObject so it can be materialized."""
    obj = create_object(CompanionObject, key=companion.name, nohome=True)
    companion.objectdb = obj
    companion.save(update_fields=["objectdb"])
    return companion


class CompanionOrderRoundTickTests(TestCase):
    """Tests that the NPC round-tick respects CompanionOrder directives."""

    def setUp(self):
        self.archetype = CompanionArchetypeFactory(name="OrderTickBeast")
        self.companion = _bind_with_object(CompanionFactory(archetype=self.archetype))
        self.encounter = CombatEncounterFactory()
        self.threat_pool = ThreatPoolFactory()
        self.participant = CombatParticipant.objects.create(
            character_sheet=self.companion.owner,
            encounter=self.encounter,
            status=ParticipantStatus.ACTIVE,
        )

        # Materialize the companion as an ALLY opponent
        self.ally_opponent = materialize_companion_as_combat_opponent(
            self.companion,
            self.encounter,
            threat_pool=self.threat_pool,
        )

        # Create a threat pool entry so the companion has something to attack with
        ThreatPoolEntryFactory(
            pool=self.threat_pool,
            name="Bite",
            attack_category="physical",
        )

        # Add two enemy opponents
        self.enemy_a = CombatOpponent.objects.create(
            encounter=self.encounter,
            name="Goblin A",
            tier="mook",
            health=20,
            max_health=20,
            soak_value=0,
            threat_pool=self.threat_pool,
            allegiance=CombatAllegiance.ENEMY,
            status=OpponentStatus.ACTIVE,
        )
        self.enemy_b = CombatOpponent.objects.create(
            encounter=self.encounter,
            name="Goblin B",
            tier="mook",
            health=20,
            max_health=20,
            soak_value=0,
            threat_pool=self.threat_pool,
            allegiance=CombatAllegiance.ENEMY,
            status=OpponentStatus.ACTIVE,
        )

        self.encounter.round_number = 1
        self.encounter.status = RoundStatus.DECLARING
        self.encounter.save(update_fields=["round_number", "status"])

    def test_attack_target_directs_companion_to_specific_enemy(self):
        """Ordering ATTACK_TARGET on enemy_b makes the companion target it."""
        order_companion(
            companion=self.companion,
            order_kind=CompanionOrderKind.ATTACK_TARGET,
            encounter=self.encounter,
            round_number=1,
            target_opponent=self.enemy_b,
        )

        actions = select_npc_actions(self.encounter)

        companion_actions = [a for a in actions if a.opponent_id == self.ally_opponent.pk]
        self.assertTrue(len(companion_actions) > 0)
        for action in companion_actions:
            self.assertIn(self.enemy_b, list(action.opponent_targets.all()))

    def test_hold_skips_companion_action(self):
        """Ordering HOLD makes the companion skip the round entirely."""
        order_companion(
            companion=self.companion,
            order_kind=CompanionOrderKind.HOLD,
            encounter=self.encounter,
            round_number=1,
        )

        actions = select_npc_actions(self.encounter)

        companion_actions = [a for a in actions if a.opponent_id == self.ally_opponent.pk]
        self.assertEqual(len(companion_actions), 0)

    def test_no_order_auto_attacks_unchanged(self):
        """Without an order, the companion auto-attacks (regression check)."""
        actions = select_npc_actions(self.encounter)

        companion_actions = [a for a in actions if a.opponent_id == self.ally_opponent.pk]
        self.assertTrue(len(companion_actions) > 0)

    def test_attack_target_dead_enemy_raises(self):
        """Ordering ATTACK_TARGET on a dead enemy is rejected by the service."""
        from world.companions.services import CompanionOrderError

        self.enemy_b.status = OpponentStatus.DEFEATED
        self.enemy_b.save(update_fields=["status"])

        with self.assertRaises(CompanionOrderError):
            order_companion(
                companion=self.companion,
                order_kind=CompanionOrderKind.ATTACK_TARGET,
                encounter=self.encounter,
                round_number=1,
                target_opponent=self.enemy_b,
            )
