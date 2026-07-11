"""Tests for mirror_npc_regard_event_to_track — the #2013 bridge (#2039)."""

from django.test import TestCase

from world.npc_services.constants import NpcRegardEventReason
from world.npc_services.regard import record_npc_regard_event
from world.relationships.constants import TrackSystemKey
from world.relationships.models import (
    CharacterRelationship,
    RelationshipTrack,
    RelationshipTrackProgress,
)
from world.scenes.factories import PersonaFactory


class NpcRegardMirrorBridgeTests(TestCase):
    def setUp(self):
        RelationshipTrack.objects.get_or_create(
            system_key=TrackSystemKey.REGARD,
            defaults={"name": "Regard", "slug": "regard", "sign": "positive"},
        )
        RelationshipTrack.objects.get_or_create(
            system_key=TrackSystemKey.FRICTION,
            defaults={"name": "Friction", "slug": "friction", "sign": "negative"},
        )

    def test_negative_event_mirrors_onto_friction_track(self):
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
        friction_track = RelationshipTrack.objects.get(system_key=TrackSystemKey.FRICTION)
        progress = RelationshipTrackProgress.objects.get(
            relationship=relationship,
            track=friction_track,
        )
        self.assertEqual(progress.developed_points, 10)

    def test_positive_event_mirrors_onto_regard_track(self):
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
        regard_track = RelationshipTrack.objects.get(system_key=TrackSystemKey.REGARD)
        progress = RelationshipTrackProgress.objects.get(
            relationship=relationship,
            track=regard_track,
        )
        self.assertEqual(progress.developed_points, 8)

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
        friction_track = RelationshipTrack.objects.get(system_key=TrackSystemKey.FRICTION)
        progress = RelationshipTrackProgress.objects.get(
            relationship=relationship,
            track=friction_track,
        )
        self.assertEqual(progress.developed_points, 10)
