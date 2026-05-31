"""Tests for PC portrait fields on ParticipantSerializer (#630).

A participant's portrait resolves through the character's IDENTITY — the
primary persona's thumbnail — mirroring the opponent portrait wired in #554
(`test_opponent_portrait_serializer.py`). No portrait field is added to the
participant row; the source of truth is `CharacterSheet.primary_persona`.
"""

from __future__ import annotations

from django.test import TestCase

from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.serializers import ParticipantSerializer
from world.combat.views import CombatEncounterViewSet
from world.roster.factories import PlayerMediaFactory


class ParticipantPortraitSerializerTests(TestCase):
    def test_primary_persona_with_thumbnail_exposes_media_and_direct_url(self) -> None:
        media = PlayerMediaFactory()
        participant = CombatParticipantFactory()
        persona = participant.character_sheet.primary_persona
        persona.thumbnail = media
        persona.thumbnail_url = "https://cdn.example/pc.png"
        persona.save(update_fields=["thumbnail", "thumbnail_url"])

        data = ParticipantSerializer(participant).data
        self.assertEqual(data["thumbnail_media_url"], media.cloudinary_url)
        self.assertEqual(data["thumbnail_url"], "https://cdn.example/pc.png")

    def test_primary_persona_without_thumbnail_returns_none_and_blank(self) -> None:
        # CharacterSheetFactory creates the PRIMARY persona with no thumbnail.
        participant = CombatParticipantFactory()

        data = ParticipantSerializer(participant).data
        self.assertIsNone(data["thumbnail_media_url"])
        self.assertEqual(data["thumbnail_url"], "")


class ParticipantPortraitQueryCountTests(TestCase):
    """The portrait must resolve through the prefetched cached accessor with
    no per-participant query (the #630 N+1 guarantee)."""

    def test_resolving_thumbnails_is_n_plus_one_free(self) -> None:
        encounter = CombatEncounterFactory()
        media = PlayerMediaFactory()
        for _ in range(3):
            participant = CombatParticipantFactory(encounter=encounter)
            persona = participant.character_sheet.primary_persona
            persona.thumbnail = media
            persona.save(update_fields=["thumbnail"])

        # Load through the real viewset queryset (populates participants_cached
        # + the nested cached_payload_personas prefetch with thumbnail joined).
        loaded = CombatEncounterViewSet()._base_queryset().get(pk=encounter.pk)
        participants = loaded.participants_cached
        self.assertEqual(len(participants), 3)

        serializer = ParticipantSerializer(participants, many=True)
        with self.assertNumQueries(0):
            data = serializer.data

        self.assertTrue(
            all(row["thumbnail_media_url"] == media.cloudinary_url for row in data),
            "every participant portrait should resolve from the prefetch",
        )
