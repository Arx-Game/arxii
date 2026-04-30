"""Tests for PendingApplicationSerializer."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from web.api.serializers import PendingApplicationSerializer
from world.roster.models import ApplicationStatus, RosterApplication


class PendingApplicationSerializerTests(TestCase):
    def test_serializes_pending_application(self) -> None:
        account = AccountFactory()
        character = CharacterFactory(db_key="Lyra")
        app = RosterApplication.objects.create(
            player_data=account.player_data,
            character=character,
            application_text="please",
            status=ApplicationStatus.PENDING,
        )
        data = PendingApplicationSerializer(app).data
        assert data["id"] == app.id
        assert data["character_name"] == "Lyra"
        assert data["status"] == "pending"
        assert data["applied_date"] is not None
