"""
Tests for roster model managers.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.roster.factories import (
    CharacterFactory,
    PlayerDataFactory,
    RosterEntryFactory,
)
from world.roster.models import ApplicationStatus, RosterApplication


class RosterApplicationManagerTestCase(TestCase):
    """Test the custom manager methods"""

    def setUp(self):
        """Set up test data for each test"""
        self.player_data = PlayerDataFactory()
        self.staff_data = PlayerDataFactory()

        self.character1 = CharacterFactory()
        self.character2 = CharacterFactory()

        RosterEntryFactory(character=self.character1)
        RosterEntryFactory(character=self.character2)

    def test_pending_applications_query(self):
        """Test the pending() manager method"""
        # Create applications with different statuses
        pending_app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character1,
            application_text="Pending app",
            status=ApplicationStatus.PENDING,
        )
        RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character2,
            application_text="Approved app",
            status=ApplicationStatus.APPROVED,
        )

        pending_apps = RosterApplication.objects.pending()

        self.assertEqual(pending_apps.count(), 1)
        self.assertEqual(pending_apps.first(), pending_app)

    def test_for_character_query(self):
        """Test the for_character() manager method"""
        app1 = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character1,
            application_text="App for char1",
        )
        RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character2,
            application_text="App for char2",
        )

        char1_apps = RosterApplication.objects.for_character(self.character1)

        self.assertEqual(char1_apps.count(), 1)
        self.assertEqual(char1_apps.first(), app1)

    def test_for_player_query(self):
        """Test the for_player() manager method"""
        app1 = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character1,
            application_text="Player app",
        )
        RosterApplication.objects.create(
            player_data=self.staff_data,
            character=self.character2,
            application_text="Staff app",
        )

        player_apps = RosterApplication.objects.for_player(self.player_data)

        self.assertEqual(player_apps.count(), 1)
        self.assertEqual(player_apps.first(), app1)

    def test_awaiting_review_query(self):
        """Test the awaiting_review() manager method returns pending apps in order"""
        # Create apps at different times
        old_app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character1,
            application_text="Old app",
        )
        old_app.applied_date = timezone.now() - timedelta(days=2)
        old_app.save()

        new_app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character2,
            application_text="New app",
        )

        awaiting = list(RosterApplication.objects.awaiting_review())

        self.assertEqual(len(awaiting), 2)
        self.assertEqual(awaiting[0], old_app)  # Older app first
        self.assertEqual(awaiting[1], new_app)

    def test_recently_reviewed_query(self):
        """Test the recently_reviewed() manager method"""
        # Create reviewed application within the time window
        recent_app = RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character1,
            application_text="Recent app",
            status=ApplicationStatus.APPROVED,
            reviewed_date=timezone.now() - timedelta(days=3),
        )

        # Create old reviewed application outside the time window
        RosterApplication.objects.create(
            player_data=self.player_data,
            character=self.character2,
            application_text="Old app",
            status=ApplicationStatus.DENIED,
            reviewed_date=timezone.now() - timedelta(days=10),
        )

        recent_apps = RosterApplication.objects.recently_reviewed(days=7)

        self.assertEqual(recent_apps.count(), 1)
        self.assertEqual(recent_apps.first(), recent_app)
