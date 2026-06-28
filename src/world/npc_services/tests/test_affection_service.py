"""Tests for the reusable NPC affection adjustment helper."""

from django.test import TestCase

from world.npc_services.models import NPCStanding
from world.npc_services.services import adjust_npc_affection
from world.scenes.factories import PersonaFactory


class AdjustNpcAffectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pc = PersonaFactory()
        cls.npc = PersonaFactory()

    def test_applies_delta_to_existing_standing(self):
        standing = NPCStanding.objects.create(persona=self.pc, npc_persona=self.npc, affection=10)
        new = adjust_npc_affection(self.pc, self.npc, delta=5)
        standing.refresh_from_db()
        self.assertEqual(new, 15)
        self.assertEqual(standing.affection, 15)

    def test_creates_row_when_absent(self):
        self.assertFalse(NPCStanding.objects.filter(persona=self.pc, npc_persona=self.npc).exists())
        new = adjust_npc_affection(self.pc, self.npc, delta=3)
        self.assertEqual(new, 3)
        self.assertEqual(
            NPCStanding.objects.get(persona=self.pc, npc_persona=self.npc).affection, 3
        )

    def test_negative_delta_disliked(self):
        NPCStanding.objects.create(persona=self.pc, npc_persona=self.npc, affection=2)
        new = adjust_npc_affection(self.pc, self.npc, delta=-10)
        self.assertEqual(new, -8)

    def test_delta_zero_returns_current_and_no_row_change(self):
        NPCStanding.objects.create(persona=self.pc, npc_persona=self.npc, affection=7)
        result = adjust_npc_affection(self.pc, self.npc, delta=0)
        self.assertEqual(result, 7)
        standing = NPCStanding.objects.get(persona=self.pc, npc_persona=self.npc)
        self.assertEqual(standing.affection, 7)

    def test_delta_zero_creates_row_at_zero(self):
        result = adjust_npc_affection(self.pc, self.npc, delta=0)
        self.assertEqual(result, 0)
        self.assertTrue(NPCStanding.objects.filter(persona=self.pc, npc_persona=self.npc).exists())
