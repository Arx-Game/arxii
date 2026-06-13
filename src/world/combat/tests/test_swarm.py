"""Swarm tier mechanics (#875): count-pool helpers, damage, offense, attrition arc."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ENTITY_TYPE_NPC, EncounterStatus, OpponentStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    SwarmOpponentFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.services import (
    apply_damage_to_opponent,
    resolve_round,
    select_npc_actions,
    swarm_attack_count,
    swarm_kills,
)
from world.vitals.models import CharacterVitals


class SwarmHelperTests(TestCase):
    def test_swarm_kills_floor_with_minimum_one(self):
        # 5 damage per body: 12 damage clears 2 bodies.
        self.assertEqual(swarm_kills(12, body_toughness=5), 2)

    def test_swarm_kills_landing_hit_always_clears_one(self):
        # Damage below one body's toughness still clears a single body.
        self.assertEqual(swarm_kills(3, body_toughness=5), 1)

    def test_swarm_kills_zero_damage_clears_nothing(self):
        self.assertEqual(swarm_kills(0, body_toughness=5), 0)

    def test_swarm_attack_count_scales_with_count(self):
        # 30 bodies / 6 per attack = 5 attacks, capped at 4 acting PCs.
        self.assertEqual(swarm_attack_count(30, bodies_per_attack=6, active_pc_count=4), 4)

    def test_swarm_attack_count_shrinks_as_count_drops(self):
        self.assertEqual(swarm_attack_count(6, bodies_per_attack=6, active_pc_count=4), 1)

    def test_swarm_attack_count_zero_when_no_bodies_or_no_targets(self):
        self.assertEqual(swarm_attack_count(0, bodies_per_attack=6, active_pc_count=4), 0)
        self.assertEqual(swarm_attack_count(10, bodies_per_attack=6, active_pc_count=0), 0)


class SwarmDamageTests(TestCase):
    def test_damage_reduces_count_not_health_and_ignores_soak(self):
        swarm = SwarmOpponentFactory(swarm_count=30, max_swarm_count=30, body_toughness=5)
        result = apply_damage_to_opponent(swarm, 12)  # 12 // 5 = 2 bodies
        swarm.refresh_from_db()
        self.assertEqual(result.kills, 2)
        self.assertEqual(swarm.swarm_count, 28)
        self.assertEqual(swarm.health, 1)  # untouched
        self.assertEqual(swarm.status, OpponentStatus.ACTIVE)

    def test_swarm_defeated_when_count_hits_zero(self):
        swarm = SwarmOpponentFactory(swarm_count=2, max_swarm_count=30, body_toughness=5)
        result = apply_damage_to_opponent(swarm, 100)  # would clear 20, clamped to 2
        swarm.refresh_from_db()
        self.assertEqual(swarm.swarm_count, 0)
        self.assertTrue(result.defeated)
        self.assertEqual(swarm.status, OpponentStatus.DEFEATED)


class SwarmOffenseTests(TestCase):
    """Swarm emits volume-scaled CombatOpponentActions via select_npc_actions."""

    def test_high_count_swarm_emits_multiple_attacks(self):
        """30 bodies / 6 per attack = 5 raw, capped at 2 acting PCs → 2 actions."""
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)
        swarm = SwarmOpponentFactory(
            encounter=encounter,
            swarm_count=30,
            bodies_per_attack=6,
            threat_pool=pool,
        )
        # Two actable PC participants (no vitals row → is_dead=False, no AWARENESS
        # CapabilityType → can_act=True).
        CombatParticipantFactory(encounter=encounter)
        CombatParticipantFactory(encounter=encounter)

        actions = select_npc_actions(encounter)

        swarm_actions = [a for a in actions if a.opponent_id == swarm.pk]
        self.assertEqual(len(swarm_actions), 2)


class SwarmResolutionTests(TestCase):
    """End-to-end: a multi-action swarm resolves multiple attacks per round (#875).

    Task 6 dropped the unique (opponent, round_number) constraint so a swarm can
    emit several CombatOpponentActions in one round. This proves the resolution
    path (resolve_round → _resolve_actions) does NOT collapse that volume back to
    a single action — both swarm attacks resolve into distinct outcomes and both
    PCs take damage.
    """

    def test_swarm_resolves_multiple_attacks_per_round(self):
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        # base_damage applied directly (no defense_check_type in resolve_round call).
        ThreatPoolEntryFactory(pool=pool, base_damage=10)
        swarm = SwarmOpponentFactory(
            encounter=encounter,
            swarm_count=30,
            bodies_per_attack=6,
            threat_pool=pool,
        )
        # Two acting PCs (vitals row → is_dead/can_act resolve correctly and damage
        # can land). 30 bodies / 6 per attack = 5 raw, capped at 2 acting PCs → 2.
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        CombatParticipantFactory(encounter=encounter, character_sheet=sheet_a)
        CombatParticipantFactory(encounter=encounter, character_sheet=sheet_b)
        CharacterVitals.objects.create(character_sheet=sheet_a, health=100, max_health=100)
        CharacterVitals.objects.create(character_sheet=sheet_b, health=100, max_health=100)

        # Emit the swarm's volume-scaled actions, then resolve the round.
        emitted = select_npc_actions(encounter)
        self.assertEqual(len([a for a in emitted if a.opponent_id == swarm.pk]), 2)

        result = resolve_round(encounter)

        # The swarm's two attacks resolve into two distinct NPC outcomes — the
        # volume is NOT collapsed to one at resolution.
        swarm_outcomes = [
            o
            for o in result.action_outcomes
            if o.entity_type == ENTITY_TYPE_NPC and o.entity_label == str(swarm)
        ]
        self.assertEqual(len(swarm_outcomes), 2)

        # Each attack resolved real damage against a PC (one damage result each):
        # the swarm landed two separate hits this round, not one.
        total_damage_results = sum(len(o.damage_results) for o in swarm_outcomes)
        self.assertEqual(total_damage_results, 2)
        # At least one PC visibly lost health from the swarm's volley.
        healths = [
            CharacterVitals.objects.get(character_sheet=sheet).health
            for sheet in (sheet_a, sheet_b)
        ]
        self.assertTrue(any(h < 100 for h in healths))


class SwarmAttritionArcTests(TestCase):
    """End-to-end attritional curve: repeated damage drives swarm to DEFEATED (#875)."""

    def test_swarm_attrition_to_defeat(self):
        swarm = SwarmOpponentFactory(swarm_count=20, max_swarm_count=20, body_toughness=5)
        counts = []
        for _ in range(10):
            if swarm.status == OpponentStatus.DEFEATED:
                break
            apply_damage_to_opponent(swarm, 25)  # 5 bodies/hit
            swarm.refresh_from_db()
            counts.append(swarm.swarm_count)
        self.assertEqual(swarm.swarm_count, 0)
        self.assertEqual(swarm.status, OpponentStatus.DEFEATED)
        self.assertEqual(counts, sorted(counts, reverse=True))  # monotonic decline

    def test_attack_volume_declines_with_count(self):
        hi = swarm_attack_count(30, bodies_per_attack=6, active_pc_count=4)
        lo = swarm_attack_count(6, bodies_per_attack=6, active_pc_count=4)
        self.assertGreater(hi, lo)
