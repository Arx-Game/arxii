"""Tests for the EngagementLock model — foil pairing lifecycle (#2020)."""

from django.db import IntegrityError
from django.test import TestCase

from world.combat.constants import EngagementLockStatus, LockBreakReason, LockInitiator
from world.combat.factories import (
    CombatOpponentFactory,
    EngagementLockFactory,
)
from world.combat.models import EngagementLock


class EngagementLockModelTests(TestCase):
    """EngagementLock: one active lock per opponent at a time."""

    def test_defaults(self):
        lock = EngagementLockFactory()
        self.assertEqual(lock.status, EngagementLockStatus.ACTIVE)
        self.assertEqual(lock.initiated_by, LockInitiator.THREAT)
        self.assertIsNone(lock.ended_round)
        self.assertIsNone(lock.break_reason)
        self.assertIsNone(lock.clash)

    def test_str_representation(self):
        lock = EngagementLockFactory()
        self.assertIn("active", str(lock))

    def test_only_one_active_lock_per_opponent(self):
        lock = EngagementLockFactory()
        with self.assertRaises(IntegrityError):
            EngagementLock.objects.create(
                encounter=lock.encounter,
                opponent=lock.opponent,
                participant=lock.participant,
                status=EngagementLockStatus.ACTIVE,
                initiated_by=LockInitiator.THREAT,
                started_round=1,
            )

    def test_broken_lock_allows_new_active(self):
        lock = EngagementLockFactory()
        lock.status = EngagementLockStatus.BROKEN
        lock.break_reason = LockBreakReason.DISENGAGE
        lock.ended_round = 2
        lock.save()
        # A new active lock on the same opponent should succeed
        new_lock = EngagementLock.objects.create(
            encounter=lock.encounter,
            opponent=lock.opponent,
            participant=lock.participant,
            status=EngagementLockStatus.ACTIVE,
            initiated_by=LockInitiator.PC_CHALLENGE,
            started_round=3,
        )
        self.assertEqual(new_lock.status, EngagementLockStatus.ACTIVE)


class CombatOpponentFoilFieldsTests(TestCase):
    """CombatOpponent gains has_foil_behavior + auto_lock_threshold."""

    def test_auto_lock_threshold_default(self):
        opp = CombatOpponentFactory()
        self.assertEqual(opp.auto_lock_threshold, 100)

    def test_has_foil_behavior_default_false(self):
        opp = CombatOpponentFactory()
        self.assertFalse(opp.has_foil_behavior)


class EscalationCurveInterferenceFieldTests(TestCase):
    """EscalationCurve gains interference_spike_intensity_amount."""

    def test_default(self):
        from world.combat.factories import EscalationCurveFactory

        curve = EscalationCurveFactory()
        self.assertEqual(curve.interference_spike_intensity_amount, 0)
