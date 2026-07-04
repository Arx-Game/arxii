"""Tests for the generalized debt/petition-streak fields on NPCStanding (#1718)."""

from django.test import TestCase

from world.npc_services.factories import NPCStandingFactory


class NPCStandingDebtFieldsTests(TestCase):
    def test_new_fields_default_to_zero(self):
        standing = NPCStandingFactory()
        self.assertEqual(standing.debt, 0)
        self.assertEqual(standing.debt_baseline_affection, 0)
        self.assertEqual(standing.debt_baseline_missions_completed, 0)
        self.assertEqual(standing.consecutive_failed_petitions, 0)
