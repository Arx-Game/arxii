"""Tests for RelationshipUpdateViewSet (#1485).

Exercises the four write endpoints (`first_impression`, `develop`, `capstone`,
`redistribute`) the way the web frontend hits them: a POST that resolves the
caller's puppet and dispatches through the relationship Actions. Mirrors the
``PersonaViewSet.set_active`` test pattern (``APIRequestFactory`` +
``force_authenticate`` with a puppet-bearing user).
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import TrackSign
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
)
from world.relationships.models import (
    CharacterRelationship,
    RelationshipCapstone,
    RelationshipDevelopment,
    RelationshipUpdate,
)
from world.relationships.views import RelationshipUpdateViewSet
from world.scenes.factories import PersonaFactory


def _actor_user(character):
    """A fake authenticated user whose ``puppet`` is ``character``."""
    return SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        pk=character.db_account_id,
        puppet=character,
    )


class RelationshipUpdateViewSetTests(TestCase):
    """Drive the four relationship-building verbs via the web endpoints."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        # Caller (source): a character with a primary persona.
        self.actor_character = CharacterFactory()
        self.actor_sheet = CharacterSheetFactory(character=self.actor_character)
        self.actor_persona = self.actor_sheet.primary_persona
        # Target (a second character + sheet + persona).
        self.target_character = CharacterFactory()
        self.target_sheet = CharacterSheetFactory(character=self.target_character)
        self.target_persona = PersonaFactory(character_sheet=self.target_sheet)
        self.track = RelationshipTrackFactory(sign=TrackSign.POSITIVE)
        self.factory = APIRequestFactory()

    def _post(self, action: str, puppet, payload: dict):
        url = f"/api/relationships/relationship-updates/{action}/"
        request = self.factory.post(url, payload, format="json")
        force_authenticate(request, user=_actor_user(puppet))
        view = RelationshipUpdateViewSet.as_view({"post": action})
        return view(request)

    def test_first_impression_endpoint_creates_relationship(self) -> None:
        resp = self._post(
            "first_impression",
            self.actor_character,
            {
                "target_persona_id": self.target_persona.pk,
                "track_id": self.track.pk,
                "points": 3,
                "title": "A striking introduction",
                "writeup": "They commanded the room.",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["success"])
        relationship = CharacterRelationship.objects.get(
            source=self.actor_sheet, target=self.target_sheet
        )
        self.assertTrue(relationship.is_pending)
        self.assertTrue(
            RelationshipUpdate.objects.filter(
                relationship=relationship, is_first_impression=True
            ).exists()
        )

    def test_develop_endpoint_adds_development(self) -> None:
        # Development adds permanent points up to track capacity, so seed
        # capacity directly on the progress record (the Update factory alone
        # does not bump capacity).
        relationship = CharacterRelationshipFactory(
            source=self.actor_sheet, target=self.target_sheet
        )
        from world.relationships.models import RelationshipTrackProgress

        RelationshipTrackProgress.objects.create(
            relationship=relationship,
            track=self.track,
            capacity=5,
            developed_points=0,
        )
        resp = self._post(
            "develop",
            self.actor_character,
            {
                "target_persona_id": self.target_persona.pk,
                "track_id": self.track.pk,
                "points": 2,
                "title": "Growing respect",
                "writeup": "They proved themselves.",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            RelationshipDevelopment.objects.filter(
                author=self.actor_sheet, track=self.track
            ).exists()
        )

    def test_capstone_endpoint_creates_capstone(self) -> None:
        resp = self._post(
            "capstone",
            self.actor_character,
            {
                "target_persona_id": self.target_persona.pk,
                "track_id": self.track.pk,
                "points": 10,
                "title": "A binding oath",
                "writeup": "We swore an oath that day.",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            RelationshipCapstone.objects.filter(
                author=self.actor_sheet, track=self.track, points=10
            ).exists()
        )

    def test_redistribute_endpoint_moves_points(self) -> None:
        # Seed a relationship with developed points on the source track.
        relationship = CharacterRelationshipFactory(
            source=self.actor_sheet, target=self.target_sheet
        )
        target_track = RelationshipTrackFactory(sign=TrackSign.POSITIVE)
        from world.relationships.models import RelationshipTrackProgress

        RelationshipTrackProgress.objects.create(
            relationship=relationship,
            track=self.track,
            capacity=10,
            developed_points=5,
        )
        resp = self._post(
            "redistribute",
            self.actor_character,
            {
                "target_persona_id": self.target_persona.pk,
                "source_track_id": self.track.pk,
                "target_track_id": target_track.pk,
                "points": 3,
                "title": "A shift of feeling",
                "writeup": "Respect waned.",
            },
        )
        self.assertEqual(resp.status_code, 200)
        progress = RelationshipTrackProgress.objects.get(
            relationship=relationship, track=target_track
        )
        self.assertEqual(progress.developed_points, 3)

    def test_first_impression_rejects_unknown_target_persona(self) -> None:
        resp = self._post(
            "first_impression",
            self.actor_character,
            {
                "target_persona_id": 999_999,
                "track_id": self.track.pk,
                "points": 3,
                "title": "x",
                "writeup": "y",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data["success"])

    def test_first_impression_rejects_missing_track(self) -> None:
        resp = self._post(
            "first_impression",
            self.actor_character,
            {
                "target_persona_id": self.target_persona.pk,
                "track_id": 999_999,
                "points": 3,
                "title": "x",
                "writeup": "y",
            },
        )
        self.assertEqual(resp.status_code, 400)

    def test_no_puppet_returns_400(self) -> None:
        # User with no puppet — the actor cannot be resolved.
        user = SimpleNamespace(is_authenticated=True, is_staff=False, pk=None, puppet=None)
        request = self.factory.post(
            "/api/relationships/relationship-updates/first_impression/",
            {
                "target_persona_id": self.target_persona.pk,
                "track_id": self.track.pk,
                "points": 3,
                "title": "x",
                "writeup": "y",
            },
            format="json",
        )
        force_authenticate(request, user=user)
        view = RelationshipUpdateViewSet.as_view({"post": "first_impression"})
        resp = view(request)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["message"].lower())
