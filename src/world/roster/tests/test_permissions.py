"""
Tests for roster system permission enforcement.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.roster.factories import (
    PlayerDataFactory,
    PlayerMediaFactory,
    RosterEntryFactory,
    RosterTenureFactory,
    TenureMediaFactory,
)


class PlayerMediaPermissionsTestCase(APITestCase):
    """Test permission enforcement for PlayerMedia management."""

    def setUp(self):
        # Create test accounts
        self.owner = AccountFactory(username="owner")
        self.other_user = AccountFactory(username="other_user")
        self.staff = AccountFactory(username="staff", is_staff=True)

        # Create player data for accounts
        self.owner_player_data = PlayerDataFactory(account=self.owner)
        self.other_player_data = PlayerDataFactory(account=self.other_user)
        self.staff_player_data = PlayerDataFactory(account=self.staff)

        # Create media owned by first user
        self.owner_media = PlayerMediaFactory(player_data=self.owner_player_data)
        self.other_media = PlayerMediaFactory(player_data=self.other_player_data)

    def test_media_list_public_access(self):
        """Anyone can list media (read-only access)."""
        # Unauthenticated user
        url = reverse("roster:media-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_media_detail_public_access(self):
        """Anyone can view media details."""
        url = reverse("roster:media-detail", kwargs={"pk": self.owner_media.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_media_create_requires_authentication(self):
        """Creating media requires authentication."""
        url = reverse("roster:media-list")
        data = {"title": "Test Media", "media_type": "photo"}

        # Unauthenticated cannot create
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Authenticated user can create
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(url, data, format="json")
        # Note: This will fail due to missing image file, but permission check should
        # pass
        assert response.status_code != status.HTTP_403_FORBIDDEN

    @suppress_permission_errors
    def test_media_modify_owner_only(self):
        """Only media owner can modify their media."""
        url = reverse("roster:media-detail", kwargs={"pk": self.owner_media.pk})
        data = {"title": "Updated Title"}

        # Other user cannot modify
        self.client.force_authenticate(user=self.other_user)
        response = self.client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Owner can modify
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_media_modify_staff_permission(self):
        """Staff can always modify media."""
        url = reverse("roster:media-detail", kwargs={"pk": self.owner_media.pk})
        data = {"title": "Staff Updated Title"}

        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_media_delete_owner_only(self):
        """Only media owner can delete their media."""
        media_to_delete = PlayerMediaFactory(player_data=self.owner_player_data)
        url = reverse("roster:media-detail", kwargs={"pk": media_to_delete.pk})

        # Other user cannot delete
        self.client.force_authenticate(user=self.other_user)
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Owner can delete
        self.client.force_authenticate(user=self.owner)
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    @suppress_permission_errors
    def test_associate_tenure_owner_only(self):
        """Only media owner can associate media with tenure."""
        owner_tenure = RosterTenureFactory(player_data=self.owner_player_data)
        other_tenure = RosterTenureFactory(player_data=self.other_player_data)

        # Test other user trying to associate owner's media
        url = reverse(
            "roster:media-associate-tenure",
            kwargs={"pk": self.owner_media.pk},
        )
        data = {"tenure_id": other_tenure.id}

        # Other user cannot associate (fails permission check before tenure lookup)
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Owner can associate
        self.client.force_authenticate(user=self.owner)
        data = {"tenure_id": owner_tenure.id}
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    @suppress_permission_errors
    def test_set_profile_picture_owner_only(self):
        """Only media owner can set media as profile picture."""
        url = reverse(
            "roster:media-set-profile-picture",
            kwargs={"pk": self.owner_media.pk},
        )

        # Other user cannot set profile picture
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Owner can set profile picture
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT


class RosterEntryPermissionsTestCase(APITestCase):
    """Test permission enforcement for RosterEntry management."""

    def setUp(self):
        # Create test accounts
        self.player = AccountFactory(username="player")
        self.other_player = AccountFactory(username="other_player")
        self.staff = AccountFactory(username="staff", is_staff=True)

        # Create player data
        self.player_data = PlayerDataFactory(account=self.player)
        self.other_player_data = PlayerDataFactory(account=self.other_player)

        # Create roster entry and tenure
        self.roster_entry = RosterEntryFactory()
        self.tenure = RosterTenureFactory(
            roster_entry=self.roster_entry,
            player_data=self.player_data,
        )

        # Create tenure media for profile picture test
        self.tenure_media = TenureMediaFactory(tenure=self.tenure)

    def test_roster_entry_list_public_access(self):
        """Anyone can list roster entries."""
        url = reverse("roster:entries-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_roster_entry_detail_public_access(self):
        """Anyone can view roster entry details."""
        url = reverse("roster:entries-detail", kwargs={"pk": self.roster_entry.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_set_profile_picture_player_only(self):
        """Only current player of character can set profile picture."""
        url = reverse(
            "roster:entries-set-profile-picture",
            kwargs={"pk": self.roster_entry.pk},
        )
        data = {"tenure_media_id": self.tenure_media.id}

        # Other player cannot set profile picture
        self.client.force_authenticate(user=self.other_player)
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Current player can set profile picture
        self.client.force_authenticate(user=self.player)
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_set_profile_picture_staff_permission(self):
        """Staff can always set profile pictures."""
        url = reverse(
            "roster:entries-set-profile-picture",
            kwargs={"pk": self.roster_entry.pk},
        )
        data = {"tenure_media_id": self.tenure_media.id}

        self.client.force_authenticate(user=self.staff)
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_204_NO_CONTENT


class RosterPermissionsTestCase(APITestCase):
    """Test permission enforcement for Roster management."""

    def test_roster_list_public_access(self):
        """Anyone can list rosters."""
        url = reverse("roster:rosters-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_roster_detail_public_access(self):
        """Anyone can view roster details."""
        from world.roster.factories import RosterFactory

        roster = RosterFactory()
        url = reverse("roster:rosters-detail", kwargs={"pk": roster.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK


class QuerysetPermissionsTestCase(APITestCase):
    """Test that querysets properly filter based on user permissions."""

    def setUp(self):
        # Create test accounts
        self.user1 = AccountFactory(username="user1")
        self.user2 = AccountFactory(username="user2")
        self.staff = AccountFactory(username="staff", is_staff=True)

        # Create player data
        self.user1_data = PlayerDataFactory(account=self.user1)
        self.user2_data = PlayerDataFactory(account=self.user2)

        # Create media for each user
        self.user1_media = PlayerMediaFactory(player_data=self.user1_data)
        self.user2_media = PlayerMediaFactory(player_data=self.user2_data)

    def test_user_sees_only_own_media(self):
        """Users should only see their own media when authenticated."""
        url = reverse("roster:media-list")

        # User1 should only see their own media
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == self.user1_media.id

        # User2 should only see their own media
        self.client.force_authenticate(user=self.user2)
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == self.user2_media.id

    def test_staff_sees_all_media(self):
        """Staff should see all media."""
        url = reverse("roster:media-list")

        self.client.force_authenticate(user=self.staff)
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2  # Both users' media

    def test_unauthenticated_sees_no_media(self):
        """Unauthenticated users should see no media in list (no player_data)."""
        url = reverse("roster:media-list")

        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0  # No media for unauthenticated users
