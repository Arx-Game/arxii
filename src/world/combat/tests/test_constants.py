"""Tests for combat constants — foil duel additions (#2020)."""

from django.test import SimpleTestCase

from flows.constants import EventName
from world.combat.constants import (
    CombatManeuver,
    EngagementLockStatus,
    LockBreakReason,
    LockInitiator,
    SurgeTriggerKind,
)


class FoilDuelConstantsTests(SimpleTestCase):
    """Verify the new constants exist with correct values."""

    def test_surge_trigger_kind_interference(self):
        self.assertEqual(SurgeTriggerKind.INTERFERENCE, "interference")

    def test_combat_maneuver_engage(self):
        self.assertEqual(CombatManeuver.ENGAGE, "engage")

    def test_combat_maneuver_disengage(self):
        self.assertEqual(CombatManeuver.DISENGAGE, "disengage")

    def test_engagement_lock_status_choices(self):
        self.assertEqual(
            {c[0] for c in EngagementLockStatus.choices},
            {"active", "broken", "ended"},
        )

    def test_lock_initiator_choices(self):
        self.assertEqual(
            {c[0] for c in LockInitiator.choices},
            {"threat", "pc_challenge", "gm_declared"},
        )

    def test_lock_break_reason_choices(self):
        self.assertEqual(
            {c[0] for c in LockBreakReason.choices},
            {"defeat", "flee", "disengage", "interference", "expired"},
        )

    def test_flow_events_exist(self):
        self.assertEqual(EventName.ENGAGEMENT_LOCK_FORMED, "engagement_lock_formed")
        self.assertEqual(EventName.ENGAGEMENT_LOCK_BROKEN, "engagement_lock_broken")
