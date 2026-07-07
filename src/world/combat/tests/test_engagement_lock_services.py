"""Tests for engagement lock service functions — formation and breaking (#2020)."""

from django.test import TestCase

from world.combat.constants import EngagementLockStatus, LockBreakReason, LockInitiator
from world.combat.engagement_locks import (
    break_engagement_lock,
    check_auto_lock_formation,
    create_engagement_lock,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatRecordFactory,
)
from world.combat.models import EngagementLock


class CreateEngagementLockTests(TestCase):
    """create_engagement_lock makes an ACTIVE lock."""

    def test_creates_active_lock(self):
        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(encounter=enc)
        part = CombatParticipantFactory(encounter=enc)
        lock = create_engagement_lock(enc, opp, part, initiated_by=LockInitiator.GM_DECLARED)
        self.assertEqual(lock.status, EngagementLockStatus.ACTIVE)
        self.assertEqual(lock.initiated_by, LockInitiator.GM_DECLARED)

    def test_no_duplicate_for_same_opponent(self):
        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(encounter=enc)
        part = CombatParticipantFactory(encounter=enc)
        lock1 = create_engagement_lock(enc, opp, part)
        lock2 = create_engagement_lock(enc, opp, part)
        self.assertEqual(lock1.pk, lock2.pk)


class CheckAutoLockFormationTests(TestCase):
    """check_auto_lock_formation creates locks when threat crosses threshold."""

    def test_threat_above_threshold_creates_lock(self):
        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(encounter=enc, auto_lock_threshold=20)
        part = CombatParticipantFactory(encounter=enc)
        ThreatRecordFactory(encounter=enc, opponent=opp, participant=part, threat_value=50)
        check_auto_lock_formation(enc)
        lock = EngagementLock.objects.get(encounter=enc, opponent=opp)
        self.assertEqual(lock.initiated_by, LockInitiator.THREAT)
        self.assertEqual(lock.participant, part)

    def test_threat_below_threshold_no_lock(self):
        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(encounter=enc, auto_lock_threshold=100)
        part = CombatParticipantFactory(encounter=enc)
        ThreatRecordFactory(encounter=enc, opponent=opp, participant=part, threat_value=10)
        check_auto_lock_formation(enc)
        self.assertFalse(EngagementLock.objects.filter(encounter=enc, opponent=opp).exists())

    def test_existing_active_lock_no_duplicate(self):
        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(encounter=enc, auto_lock_threshold=20)
        part = CombatParticipantFactory(encounter=enc)
        ThreatRecordFactory(encounter=enc, opponent=opp, participant=part, threat_value=50)
        check_auto_lock_formation(enc)
        check_auto_lock_formation(enc)  # second call should be a no-op
        self.assertEqual(EngagementLock.objects.filter(encounter=enc, opponent=opp).count(), 1)


class BreakEngagementLockTests(TestCase):
    """break_engagement_lock ends the lock with a reason."""

    def test_breaks_with_reason(self):
        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(encounter=enc)
        part = CombatParticipantFactory(encounter=enc)
        lock = create_engagement_lock(enc, opp, part, initiated_by=LockInitiator.GM_DECLARED)
        break_engagement_lock(lock, reason=LockBreakReason.DISENGAGE)
        lock.refresh_from_db()
        self.assertEqual(lock.status, EngagementLockStatus.BROKEN)
        self.assertEqual(lock.break_reason, LockBreakReason.DISENGAGE)
        self.assertIsNotNone(lock.ended_round)

    def test_break_non_active_is_noop(self):
        enc = CombatEncounterFactory()
        opp = CombatOpponentFactory(encounter=enc)
        part = CombatParticipantFactory(encounter=enc)
        lock = create_engagement_lock(enc, opp, part, initiated_by=LockInitiator.GM_DECLARED)
        break_engagement_lock(lock, reason=LockBreakReason.DISENGAGE)
        # Second break should be a no-op
        break_engagement_lock(lock, reason=LockBreakReason.FLEE)
        lock.refresh_from_db()
        self.assertEqual(lock.break_reason, LockBreakReason.DISENGAGE)
