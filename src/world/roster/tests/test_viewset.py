"""
Tests for roster API viewsets.
"""

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from world.roster.factories import (
    ArtistFactory,
    CharacterFactory,
    PlayerDataFactory,
    PlayerMediaFactory,
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
    TenureGalleryFactory,
    TenureMediaFactory,
)
from world.roster.models import TenureGallery, TenureMedia


class TestRosterViewSet(TestCase):
    """Tests for RosterViewSet API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()

        # Create test rosters
        self.active_roster = RosterFactory(
            name="Noble Houses",
            description="Characters from noble families",
            is_active=True,
            sort_order=1,
        )

        self.inactive_roster = RosterFactory(
            name="Inactive Roster",
            description="Not currently in play",
            is_active=False,
            sort_order=2,
        )

        # Create characters in active roster
        self.available_char1 = CharacterFactory()
        self.available_entry1 = RosterEntryFactory(
            character=self.available_char1, roster=self.active_roster
        )

        self.available_char2 = CharacterFactory()
        self.available_entry2 = RosterEntryFactory(
            character=self.available_char2, roster=self.active_roster
        )

        # Create occupied character in active roster
        self.occupied_char = CharacterFactory()
        self.occupied_entry = RosterEntryFactory(
            character=self.occupied_char, roster=self.active_roster
        )
        # Give it an active tenure
        RosterTenureFactory(
            roster_entry=self.occupied_entry,
            player_data=PlayerDataFactory(),
            player_number=1,
            # end_date is None by default, meaning active
        )

        # Create character in inactive roster
        self.inactive_char = CharacterFactory()
        self.inactive_entry = RosterEntryFactory(
            character=self.inactive_char, roster=self.inactive_roster
        )

    def test_list_rosters_returns_only_active(self):
        """Test that GET /rosters/ returns only active rosters."""
        url = reverse("roster:rosters-list")
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()

        # Should only return active roster
        assert len(data) == 1
        roster_data = data[0]
        assert roster_data["name"] == "Noble Houses"
        assert roster_data["is_active"] is True

    def test_roster_data_structure(self):
        """Test that roster data includes all expected fields."""
        url = reverse("roster:rosters-list")
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        roster_data = data[0]

        # Check all expected fields are present
        expected_fields = ["id", "name", "description", "is_active", "available_count"]
        for field in expected_fields:
            assert field in roster_data, f"Missing field: {field}"

        # Check field values
        assert roster_data["id"] == self.active_roster.id
        assert roster_data["name"] == self.active_roster.name
        assert roster_data["description"] == self.active_roster.description
        assert roster_data["is_active"] == self.active_roster.is_active

    def test_available_count_placeholder_logic(self):
        """Test that available_count returns count (placeholder until trust system)."""
        url = reverse("roster:rosters-list")
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        roster_data = data[0]

        # NOTE: available_count is currently a placeholder
        # Just verify it's an integer for now until trust system is implemented
        assert isinstance(roster_data["available_count"], int)
        assert roster_data["available_count"] >= 0

    def test_roster_ordering(self):
        """Test that rosters are ordered by sort_order then name."""
        # Create another active roster with different sort_order
        RosterFactory(
            name="Commoners",
            is_active=True,
            sort_order=0,  # Lower sort_order, should come first
        )

        url = reverse("roster:rosters-list")
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2
        assert data[0]["name"] == "Commoners"  # sort_order 0
        assert data[1]["name"] == "Noble Houses"  # sort_order 1

    def test_available_count_with_ended_tenures(self):
        """Test that characters with ended tenures are counted as available."""
        from datetime import timedelta

        from django.utils import timezone

        # Create character with ended tenure
        ended_char = CharacterFactory()
        ended_entry = RosterEntryFactory(
            character=ended_char, roster=self.active_roster
        )
        RosterTenureFactory(
            roster_entry=ended_entry,
            player_data=PlayerDataFactory(),
            player_number=1,
            start_date=timezone.now() - timedelta(days=30),
            end_date=timezone.now() - timedelta(days=1),  # Ended yesterday
        )

        url = reverse("roster:rosters-list")
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        roster_data = data[0]

        # Just verify available_count is present and valid (placeholder logic)
        assert isinstance(roster_data["available_count"], int)
        assert roster_data["available_count"] >= 0

    def test_available_count_anonymous_user(self):
        """Test that available_count works for anonymous users."""
        # Don't authenticate
        url = reverse("roster:rosters-list")
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()
        roster_data = data[0]

        # Should still return count for anonymous users
        assert "available_count" in roster_data
        assert isinstance(roster_data["available_count"], int)


class TestPlayerMediaViewSet(TestCase):
    """Tests for PlayerMediaViewSet API endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.player = PlayerDataFactory()
        self.client.force_authenticate(user=self.player.account)
        self.tenure = RosterTenureFactory(player_data=self.player)
        self.media = PlayerMediaFactory(player_data=self.player)

    def test_list_media(self):
        url = "/api/roster/media/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 1
        media_data = response.data[0]
        expected_fields = [
            "id",
            "cloudinary_public_id",
            "cloudinary_url",
            "media_type",
            "title",
            "description",
            "created_by",
            "uploaded_date",
            "updated_date",
        ]
        for field in expected_fields:
            assert field in media_data
        assert media_data["id"] == self.media.id
        assert media_data["created_by"] is None

    @patch("world.roster.views.media_views.CloudinaryGalleryService.upload_image")
    def test_create_media(self, mock_upload):
        mock_media = PlayerMediaFactory(player_data=self.player)
        mock_upload.return_value = mock_media
        url = "/api/roster/media/"
        response = self.client.post(url, {"media_type": "photo"}, format="json")
        assert response.status_code == 201
        assert response.data["id"] == mock_media.id

    @patch("world.roster.views.media_views.CloudinaryGalleryService.upload_image")
    def test_create_media_with_artist(self, mock_upload):
        artist = ArtistFactory()
        mock_media = PlayerMediaFactory(player_data=self.player, created_by=artist)
        mock_upload.return_value = mock_media
        url = "/api/roster/media/"
        response = self.client.post(
            url, {"media_type": "photo", "created_by": artist.id}, format="json"
        )
        assert response.status_code == 201
        mock_upload.assert_called_with(
            player_data=self.player,
            image_file=None,
            media_type="photo",
            title="",
            description="",
            created_by=artist,
        )
        assert response.data["created_by"]["id"] == artist.id

    def test_associate_tenure(self):
        gallery = TenureGalleryFactory(tenure=self.tenure)
        url = f"/api/roster/media/{self.media.id}/associate_tenure/"
        response = self.client.post(
            url,
            {"tenure_id": self.tenure.id, "gallery_id": gallery.id},
            format="json",
        )
        assert response.status_code == 201
        assert TenureMedia.objects.filter(
            tenure=self.tenure, media=self.media, gallery=gallery
        ).exists()

    def test_set_profile_picture(self):
        url = f"/api/roster/media/{self.media.id}/set_profile_picture/"
        response = self.client.post(url)
        assert response.status_code == 204
        self.player.refresh_from_db()
        assert self.player.profile_picture == self.media


class TestTenureGalleryViewSet(TestCase):
    """Tests for TenureGalleryViewSet API endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.player = PlayerDataFactory()
        self.client.force_authenticate(user=self.player.account)
        self.tenure = RosterTenureFactory(player_data=self.player)
        self.other_tenure = RosterTenureFactory()

    def test_create_gallery(self):
        url = "/api/roster/galleries/"
        payload = {
            "tenure_id": self.tenure.id,
            "name": "Portraits",
            "is_public": False,
            "allowed_viewers": [self.other_tenure.id],
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == 201
        gallery_id = response.data["id"]
        gallery = TenureGallery.objects.get(pk=gallery_id)
        assert gallery.name == "Portraits"
        assert not gallery.is_public
        assert list(gallery.allowed_viewers.values_list("id", flat=True)) == [
            self.other_tenure.id
        ]


class TestRosterEntrySetProfilePicture(TestCase):
    """Tests setting roster entry profile pictures."""

    def setUp(self):
        self.client = APIClient()
        self.player = PlayerDataFactory()
        self.client.force_authenticate(user=self.player.account)
        self.tenure = RosterTenureFactory(player_data=self.player)
        self.media_link = TenureMediaFactory(tenure=self.tenure)
        self.entry = self.tenure.roster_entry

    def test_set_profile_picture(self):
        url = f"/api/roster/entries/{self.entry.id}/set_profile_picture/"
        response = self.client.post(
            url, {"tenure_media_id": self.media_link.id}, format="json"
        )
        assert response.status_code == 204
        self.entry.refresh_from_db()
        assert self.entry.profile_picture == self.media_link
