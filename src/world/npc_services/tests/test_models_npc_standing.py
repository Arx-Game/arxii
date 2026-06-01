"""Tests for the unified NPCStanding model.

NPCStanding is per-(PC persona, NPC persona). Relocated here from
``world.missions.MissionGiverStanding`` (which was per-(giver, character))
in the unified NPC services framework — different shape, same role.
"""

from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from world.npc_services.factories import NPCStandingFactory
from world.npc_services.models import NPCStanding
from world.scenes.factories import PersonaFactory


class NPCStandingModelTests(TestCase):
    """(persona, npc_persona) unique; cooldown + affection."""

    def test_create_standing(self) -> None:
        persona = PersonaFactory()
        npc_persona = PersonaFactory()
        standing = NPCStandingFactory(persona=persona, npc_persona=npc_persona)
        self.assertEqual(standing.persona, persona)
        self.assertEqual(standing.npc_persona, npc_persona)
        self.assertIsNotNone(standing.available_at)

    def test_affection_defaults_to_zero(self) -> None:
        standing = NPCStandingFactory()
        self.assertEqual(standing.affection, 0)

    def test_affection_round_trips(self) -> None:
        standing = NPCStandingFactory(affection=42)
        standing.refresh_from_db()
        self.assertEqual(standing.affection, 42)

    def test_affection_accepts_negative(self) -> None:
        standing = NPCStandingFactory(affection=-5)
        standing.refresh_from_db()
        self.assertEqual(standing.affection, -5)

    def test_persona_npc_persona_uniqueness(self) -> None:
        persona = PersonaFactory()
        npc_persona = PersonaFactory()
        NPCStandingFactory(persona=persona, npc_persona=npc_persona)
        with self.assertRaises(IntegrityError):
            NPCStanding.objects.create(
                persona=persona,
                npc_persona=npc_persona,
                available_at=timezone.now() + timedelta(days=1),
            )

    def test_same_persona_different_npc_allowed(self) -> None:
        persona = PersonaFactory()
        npc_a = PersonaFactory()
        npc_b = PersonaFactory()
        NPCStandingFactory(persona=persona, npc_persona=npc_a)
        NPCStandingFactory(persona=persona, npc_persona=npc_b)
        self.assertEqual(NPCStanding.objects.filter(persona=persona).count(), 2)

    def test_available_at_nullable(self) -> None:
        standing = NPCStandingFactory(available_at=None)
        standing.refresh_from_db()
        self.assertIsNone(standing.available_at)

    def test_last_changed_at_auto_updates(self) -> None:
        standing = NPCStandingFactory(affection=0)
        first_ts = standing.last_changed_at
        standing.affection = 5
        standing.save()
        standing.refresh_from_db()
        self.assertGreater(standing.last_changed_at, first_ts)
