from django.test import TestCase

from world.combat.constants import (
    ClashActionSlot,
    ClashFlavor,
    ClashResolution,
    ClashStatus,
    LockPcRole,
)


class ClashConstantsTests(TestCase):
    def test_flavors_present(self):
        self.assertEqual(set(ClashFlavor.values), {"CLASH", "LOCK", "WARD", "BREAK"})

    def test_lock_roles_present(self):
        self.assertEqual(set(LockPcRole.values), {"SUSTAINING", "ESCAPING"})

    def test_status_and_slots(self):
        self.assertEqual(set(ClashStatus.values), {"ACTIVE", "RESOLVED"})
        self.assertEqual(set(ClashActionSlot.values), {"FOCUSED", "PASSIVE"})

    def test_resolution_tiers(self):
        self.assertEqual(
            set(ClashResolution.values),
            {"PC_DECISIVE", "PC_MARGINAL", "MUTUAL", "NPC_MARGINAL", "NPC_DECISIVE", "ABANDONED"},
        )
