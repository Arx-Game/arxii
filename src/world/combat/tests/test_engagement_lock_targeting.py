"""Tests for engagement lock targeting — locked NPC provably targets locked PC (#2020)."""

from django.test import TestCase

from world.combat.constants import (
    EncounterType,
    EngagementLockStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EngagementLockFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.services import select_npc_actions
from world.scenes.constants import RoundStatus


class LockNarrowingTests(TestCase):
    """An active EngagementLock narrows NPC targeting to the locked PC."""

    def test_locked_npc_targets_only_locked_pc(self):
        enc = CombatEncounterFactory(
            encounter_type=EncounterType.PARTY_COMBAT,
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=pool,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            weight=10,
        )
        opp = CombatOpponentFactory(encounter=enc, threat_pool=pool)
        CombatParticipantFactory(encounter=enc)
        pc_b = CombatParticipantFactory(encounter=enc)
        # Lock the opponent to pc_b
        EngagementLockFactory(
            encounter=enc,
            opponent=opp,
            participant=pc_b,
            status=EngagementLockStatus.ACTIVE,
        )
        actions = select_npc_actions(enc)
        # The opponent should have exactly one action, targeting pc_b
        opp_action = actions[0]
        self.assertEqual(list(opp_action.targets.all()), [pc_b])

    def test_no_lock_uses_normal_selection(self):
        enc = CombatEncounterFactory(
            encounter_type=EncounterType.PARTY_COMBAT,
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=pool,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.RANDOM,
            weight=10,
        )
        CombatOpponentFactory(encounter=enc, threat_pool=pool)
        pc_a = CombatParticipantFactory(encounter=enc)
        pc_b = CombatParticipantFactory(encounter=enc)
        actions = select_npc_actions(enc)
        # Without a lock, the opponent can target either PC
        targets = list(actions[0].targets.all())
        self.assertEqual(len(targets), 1)
        self.assertIn(targets[0], [pc_a, pc_b])
