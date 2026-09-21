"""Tests for mirror_npc_regard_event -- the #2013 bridge (#2039, #3957)."""

from django.test import TestCase

from world.npc_services.constants import NpcRegardEventReason
from world.npc_services.regard import record_npc_regard_event
from world.relationships.models import CharacterRelationship
from world.scenes.factories import PersonaFactory


class NpcRegardMirrorBridgeTests(TestCase):
    def test_negative_event_mirrors_onto_conflict(self):
        npc = PersonaFactory()
        pc = PersonaFactory()
        record_npc_regard_event(
            holder_persona=npc,
            target=pc,
            amount=-10,
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
        )
        # #2013 reads source=PC's own sheet, target=NPC's sheet (escalation.py:502-509).
        relationship = CharacterRelationship.objects.get(
            source=pc.character_sheet,
            target=npc.character_sheet,
        )
        self.assertEqual(relationship.conflict, 10)
        self.assertEqual(relationship.affection, 0)

    def test_positive_event_mirrors_onto_affection(self):
        npc = PersonaFactory()
        pc = PersonaFactory()
        record_npc_regard_event(
            holder_persona=npc,
            target=pc,
            amount=8,
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
        )
        relationship = CharacterRelationship.objects.get(
            source=pc.character_sheet,
            target=npc.character_sheet,
        )
        self.assertEqual(relationship.affection, 8)
        self.assertEqual(relationship.conflict, 0)

    def test_second_event_accumulates_not_dedups(self):
        npc = PersonaFactory()
        pc = PersonaFactory()
        record_npc_regard_event(
            holder_persona=npc,
            target=pc,
            amount=-5,
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
        )
        record_npc_regard_event(
            holder_persona=npc,
            target=pc,
            amount=-5,
            reason=NpcRegardEventReason.GM_MANUAL_ADJUSTMENT,
        )
        relationship = CharacterRelationship.objects.get(
            source=pc.character_sheet,
            target=npc.character_sheet,
        )
        self.assertEqual(relationship.conflict, 10)
