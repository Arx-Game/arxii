"""Opponent-vs-opponent damage: an ALLY summon attacks ENEMY opponents (#1584 Task 7b).

Task 7 made NPC *targeting* allegiance-aware, but the damage path stayed
PC-shaped: ``CombatOpponentAction.targets`` is a M2M to ``CombatParticipant``
only, so an ALLY summon selected no target and dealt no damage. These tests cover
the new ``opponent_targets`` relation + resolution branch, and the gate that keeps
ENEMY-vs-live-PC behaviour unchanged.
"""

from django.test import TestCase, tag

from world.combat.constants import CombatAllegiance
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
)
from world.combat.services import _resolve_npc_action, select_npc_actions
from world.scenes.constants import RoundStatus


class OpponentVsOpponentTargetingTests(TestCase):
    """select_npc_actions routes a summon at ENEMY opponents (non-Postgres)."""

    def test_ally_summon_targets_enemy_opponent(self) -> None:
        """An ALLY summon (empty participant pool) routes to the ENEMY opponent."""
        enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        enemy = CombatOpponentFactory(
            encounter=enc,
            allegiance=CombatAllegiance.ENEMY,
            health=50,
            max_health=50,
            soak_value=0,
        )
        summon = CombatOpponentFactory(encounter=enc, allegiance=CombatAllegiance.ALLY)
        ThreatPoolEntryFactory(pool=summon.threat_pool, base_damage=15)

        actions = select_npc_actions(enc)
        summon_actions = [a for a in actions if a.opponent_id == summon.pk]

        self.assertTrue(summon_actions)
        action = summon_actions[0]
        self.assertIn(enemy, list(action.opponent_targets.all()))
        self.assertEqual(list(action.targets.all()), [])

    def test_enemy_with_live_pc_still_targets_pc(self) -> None:
        """Decision #1 gate: an ENEMY with a live PC targets the PC, not opponents."""
        enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        pc = CombatParticipantFactory(encounter=enc)
        enemy = CombatOpponentFactory(encounter=enc, allegiance=CombatAllegiance.ENEMY)
        # An ALLY summon is also present (a candidate opponent-target for the enemy);
        # the gate must keep the enemy on the PC anyway.
        CombatOpponentFactory(encounter=enc, allegiance=CombatAllegiance.ALLY)
        ThreatPoolEntryFactory(pool=enemy.threat_pool)

        actions = select_npc_actions(enc)
        enemy_actions = [a for a in actions if a.opponent_id == enemy.pk]

        self.assertTrue(enemy_actions)
        action = enemy_actions[0]
        self.assertIn(pc, list(action.targets.all()))
        self.assertEqual(list(action.opponent_targets.all()), [])

    def test_no_valid_target_creates_no_action(self) -> None:
        """Empty-pool guard: a summon with no enemy creates no CombatOpponentAction."""
        enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        summon = CombatOpponentFactory(encounter=enc, allegiance=CombatAllegiance.ALLY)
        ThreatPoolEntryFactory(pool=summon.threat_pool)

        actions = select_npc_actions(enc)

        self.assertEqual([a for a in actions if a.opponent_id == summon.pk], [])


@tag("postgres")
class OpponentVsOpponentDamageTests(TestCase):
    """Resolving an ALLY summon's action drops the ENEMY opponent's health (#1584).

    Postgres-only: the resolution path drives ``apply_damage_to_opponent``, which
    emits DAMAGE_PRE_APPLY and touches condition queries that use PG-only SQL.
    """

    def test_summon_attack_drops_enemy_health(self) -> None:
        enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        enemy = CombatOpponentFactory(
            encounter=enc,
            allegiance=CombatAllegiance.ENEMY,
            health=50,
            max_health=50,
            soak_value=0,
        )
        summon = CombatOpponentFactory(encounter=enc, allegiance=CombatAllegiance.ALLY)
        ThreatPoolEntryFactory(pool=summon.threat_pool, base_damage=15)

        actions = select_npc_actions(enc)
        summon_action = next(a for a in actions if a.opponent_id == summon.pk)

        outcome = _resolve_npc_action(summon, summon_action, None, None)

        enemy.refresh_from_db()
        self.assertLess(enemy.health, 50)
        self.assertTrue(any(r.damage_dealt > 0 for r in outcome.damage_results))
