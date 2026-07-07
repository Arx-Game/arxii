"""E2E journey: foil duel within a group fight (#2020).

Tests the full DoD: 3 PCs + boss + foil; foil locked to PC-2 ->
foil provably targets PC-2 across rounds; damage creates threat;
auto-lock from threshold; foil defeat breaks lock with reason=DEFEAT.
"""

from django.test import TestCase

from world.combat.constants import (
    EngagementLockStatus,
    LockBreakReason,
    LockInitiator,
    TargetingMode,
    TargetSelection,
)
from world.combat.engagement_locks import (
    break_engagement_lock,
    check_auto_lock_formation,
    create_engagement_lock,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
    ThreatRecordFactory,
)
from world.combat.models import EngagementLock, ThreatRecord
from world.combat.services import apply_damage_to_opponent, select_npc_actions
from world.scenes.constants import RoundStatus


class FoilDuelE2ETests(TestCase):
    """Full journey: foil pairing, provable targeting, interference, defeat."""

    def setUp(self):
        self.enc = CombatEncounterFactory(
            encounter_type="party_combat",
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        # Three PCs
        self.pc1 = CombatParticipantFactory(encounter=self.enc)
        self.pc2 = CombatParticipantFactory(encounter=self.enc)
        self.pc3 = CombatParticipantFactory(encounter=self.enc)
        # Boss (normal targeting)
        boss_pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=boss_pool,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.RANDOM,
            weight=10,
        )
        self.boss = CombatOpponentFactory(encounter=self.enc, threat_pool=boss_pool)
        # Foil (authored, has_foil_behavior, low threshold)
        foil_pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=foil_pool,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            weight=10,
        )
        self.foil = CombatOpponentFactory(
            encounter=self.enc,
            threat_pool=foil_pool,
            has_foil_behavior=True,
            auto_lock_threshold=20,
        )

    def test_gm_locks_foil_to_pc2_and_npc_targets_pc2(self):
        """GM declares the foil locks to PC-2 -> foil provably targets PC-2."""
        create_engagement_lock(
            self.enc, self.foil, self.pc2, initiated_by=LockInitiator.GM_DECLARED
        )
        actions = select_npc_actions(self.enc)
        foil_action = next(a for a in actions if a.opponent_id == self.foil.pk)
        self.assertEqual(list(foil_action.targets.all()), [self.pc2])

    def test_foil_targets_pc2_across_multiple_rounds(self):
        """Lock persists — foil targets PC-2 on round 2 as well."""
        create_engagement_lock(
            self.enc, self.foil, self.pc2, initiated_by=LockInitiator.GM_DECLARED
        )
        select_npc_actions(self.enc)
        self.enc.round_number = 2
        self.enc.save(update_fields=["round_number"])
        actions = select_npc_actions(self.enc)
        foil_action = next(a for a in actions if a.opponent_id == self.foil.pk)
        self.assertEqual(list(foil_action.targets.all()), [self.pc2])

    def test_damage_creates_threat_record(self):
        """PC-2 dealing damage to the foil creates a ThreatRecord."""
        apply_damage_to_opponent(self.foil, 10, source_sheet=self.pc2.character_sheet)
        record = ThreatRecord.objects.get(
            encounter=self.enc, opponent=self.foil, participant=self.pc2
        )
        self.assertGreater(record.threat_value, 0)

    def test_auto_lock_formation_from_threat(self):
        """Pre-seeded threat crossing threshold creates an autonomous lock."""
        ThreatRecordFactory(
            encounter=self.enc, opponent=self.foil, participant=self.pc2, threat_value=50
        )
        check_auto_lock_formation(self.enc)
        lock = EngagementLock.objects.get(encounter=self.enc, opponent=self.foil)
        self.assertEqual(lock.initiated_by, LockInitiator.THREAT)

    def test_foil_defeat_breaks_lock_and_narrates(self):
        """Foil falling to PC-2 breaks the lock with reason=DEFEAT."""
        lock = create_engagement_lock(
            self.enc, self.foil, self.pc2, initiated_by=LockInitiator.GM_DECLARED
        )
        break_engagement_lock(lock, reason=LockBreakReason.DEFEAT)
        lock.refresh_from_db()
        self.assertEqual(lock.status, EngagementLockStatus.BROKEN)
        self.assertEqual(lock.break_reason, LockBreakReason.DEFEAT)
