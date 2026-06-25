"""Online-presence (`who`) service + the presence API (#1463)."""

from time import time
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.presence import IDLE_ACTIVE, IDLE_AWAY, IDLE_IDLE, idle_bucket, who_listing


class IdleBucketTests(TestCase):
    def test_active_under_15m_has_no_marker(self) -> None:
        assert idle_bucket(5 * 60) == IDLE_ACTIVE

    def test_idle_between_15m_and_1h(self) -> None:
        assert idle_bucket(30 * 60) == IDLE_IDLE

    def test_away_over_1h(self) -> None:
        assert idle_bucket(2 * 60 * 60) == IDLE_AWAY


class WhoListingTests(TestCase):
    def test_lists_online_character_by_active_persona_with_coarse_idle(self) -> None:
        sheet = CharacterSheetFactory()
        session = SimpleNamespace(puppet=sheet.character, cmd_last_visible=time() - 30 * 60)
        with patch("evennia.SESSION_HANDLER") as handler:
            handler.get_sessions.return_value = [session]
            entries = who_listing()
        assert len(entries) == 1
        assert entries[0].name == sheet.primary_persona.display_ic()
        assert entries[0].idle == IDLE_IDLE  # coarse bucket, never an exact duration

    def test_uses_minimum_idle_across_a_characters_sessions(self) -> None:
        sheet = CharacterSheetFactory()
        old = SimpleNamespace(puppet=sheet.character, cmd_last_visible=time() - 2 * 60 * 60)
        fresh = SimpleNamespace(puppet=sheet.character, cmd_last_visible=time() - 60)
        with patch("evennia.SESSION_HANDLER") as handler:
            handler.get_sessions.return_value = [old, fresh]
            entries = who_listing()
        assert len(entries) == 1
        assert entries[0].idle == IDLE_ACTIVE  # most-recent activity wins → active


class PresenceApiTests(APITestCase):
    def test_authenticated_get_returns_who_and_where(self) -> None:
        # ty types the factory call as the factory, not AccountDB; FactoryBoy is the
        # required test-data path, so ignore the known stub mismatch here.
        self.client.force_authenticate(user=AccountFactory())  # ty: ignore[invalid-argument-type]
        response = self.client.get("/api/areas/presence/")
        assert response.status_code == status.HTTP_200_OK
        assert "who" in response.data  # noqa: STRING_LITERAL — response key, not a discriminator
        assert "where" in response.data  # noqa: STRING_LITERAL — response key

    def test_anonymous_is_denied(self) -> None:
        response = self.client.get("/api/areas/presence/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
