import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterIdentityFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import ScenePrivacyMode
from world.scenes.factories import (
    PersonaFactory,
    SceneFactory,
    SceneGMParticipationFactory,
    SceneOwnerParticipationFactory,
    SceneParticipationFactory,
)
from world.scenes.models import Scene


def _create_owned_persona(account, **persona_kwargs):
    """Create a Persona whose character is owned by the given account via RosterTenure."""
    identity = CharacterIdentityFactory()
    player_data, _ = PlayerDataFactory._meta.model.objects.get_or_create(account=account)
    roster_entry = RosterEntryFactory(character=identity.character)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    if persona_kwargs:
        return PersonaFactory(
            character_identity=identity,
            character=identity.character,
            **persona_kwargs,
        )
    return identity.active_persona


class SceneViewActionsTestCase(APITestCase):
    """Test scene view actions and their associated permissions"""

    @classmethod
    def setUpTestData(cls):
        # Create accounts for different permission levels
        cls.owner_account = AccountFactory()
        cls.gm_account = AccountFactory()
        cls.participant_account = AccountFactory()
        cls.non_participant_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        # Create scenes for different test scenarios
        cls.active_public_scene = SceneFactory(is_active=True)
        cls.active_private_scene = SceneFactory(
            is_active=True,
            privacy_mode=ScenePrivacyMode.PRIVATE,
        )
        cls.finished_scene = SceneFactory(is_active=False)
        cls.finished_scene.finish_scene()

        # Set up participations with different roles
        SceneOwnerParticipationFactory(
            scene=cls.active_public_scene,
            account=cls.owner_account,
        )
        SceneGMParticipationFactory(
            scene=cls.active_public_scene,
            account=cls.gm_account,
        )
        SceneParticipationFactory(
            scene=cls.active_public_scene,
            account=cls.participant_account,
        )

        # Set up private scene participations
        SceneOwnerParticipationFactory(
            scene=cls.active_private_scene,
            account=cls.owner_account,
        )
        SceneParticipationFactory(
            scene=cls.active_private_scene,
            account=cls.participant_account,
        )

        # Set up finished scene participations
        SceneOwnerParticipationFactory(
            scene=cls.finished_scene,
            account=cls.owner_account,
        )

    def test_finish_action_owner_permission(self):
        """Test scene owner can finish active scenes"""
        # Create a fresh scene to avoid reusing a finished one
        test_scene = SceneFactory(is_active=True)
        SceneOwnerParticipationFactory(scene=test_scene, account=self.owner_account)

        self.client.force_authenticate(user=self.owner_account)
        url = reverse("scene-finish", kwargs={"pk": test_scene.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_200_OK
        test_scene.refresh_from_db()
        assert not test_scene.is_active
        assert test_scene.date_finished is not None

    def test_finish_action_gm_permission(self):
        """Test scene GM can finish active scenes"""
        # Create a fresh scene for GM test
        test_scene = SceneFactory(is_active=True)
        SceneGMParticipationFactory(scene=test_scene, account=self.gm_account)

        self.client.force_authenticate(user=self.gm_account)
        url = reverse("scene-finish", kwargs={"pk": test_scene.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_200_OK

    def test_finish_action_staff_permission(self):
        """Test staff can finish any scene"""
        # Create a fresh scene for staff test
        test_scene = SceneFactory(is_active=True)

        self.client.force_authenticate(user=self.staff_account)
        url = reverse("scene-finish", kwargs={"pk": test_scene.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_finish_action_participant_denied(self):
        """Test regular participant cannot finish scenes"""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("scene-finish", kwargs={"pk": self.active_public_scene.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @suppress_permission_errors
    def test_finish_action_non_participant_denied(self):
        """Test non-participant cannot finish scenes"""
        self.client.force_authenticate(user=self.non_participant_account)
        url = reverse("scene-finish", kwargs={"pk": self.active_public_scene.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_finish_action_already_finished_scene(self):
        """Test finishing already finished scene returns error"""
        self.client.force_authenticate(user=self.owner_account)
        url = reverse("scene-finish", kwargs={"pk": self.finished_scene.pk})
        response = self.client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already finished" in response.data["error"]

    def test_scene_update_owner_permission(self):
        """Test scene owner can update scenes"""
        test_scene = SceneFactory(is_active=True)
        SceneOwnerParticipationFactory(scene=test_scene, account=self.owner_account)

        self.client.force_authenticate(user=self.owner_account)
        url = reverse("scene-detail", kwargs={"pk": test_scene.pk})
        data = {"name": "Updated Scene Name", "description": "New description"}
        response = self.client.patch(
            url,
            json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK
        test_scene.refresh_from_db()
        assert test_scene.name == "Updated Scene Name"

    @suppress_permission_errors
    def test_scene_update_gm_denied(self):
        """Test scene GM cannot update scenes (only finish)"""
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("scene-detail", kwargs={"pk": self.active_public_scene.pk})
        data = {"name": "Updated Scene Name"}
        response = self.client.patch(url, data)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @suppress_permission_errors
    def test_scene_update_participant_denied(self):
        """Test regular participant cannot update scenes"""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("scene-detail", kwargs={"pk": self.active_public_scene.pk})
        data = {"name": "Updated Scene Name"}
        response = self.client.patch(url, data)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_scene_delete_owner_permission(self):
        """Test scene owner can delete scenes"""
        deletable_scene = SceneFactory()
        SceneOwnerParticipationFactory(
            scene=deletable_scene,
            account=self.owner_account,
        )

        self.client.force_authenticate(user=self.owner_account)
        url = reverse("scene-detail", kwargs={"pk": deletable_scene.pk})
        response = self.client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Scene.objects.filter(pk=deletable_scene.pk).exists()

    def test_scene_delete_staff_permission(self):
        """Test staff can delete any scene"""
        deletable_scene = SceneFactory()

        self.client.force_authenticate(user=self.staff_account)
        url = reverse("scene-detail", kwargs={"pk": deletable_scene.pk})
        response = self.client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_scene_retrieve_private_scene_participant_access(self):
        """Test participant can retrieve private scenes"""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("scene-detail", kwargs={"pk": self.active_private_scene.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == self.active_private_scene.id

    @suppress_permission_errors
    def test_scene_retrieve_private_scene_non_participant_denied(self):
        """Test non-participant cannot retrieve private scenes"""
        self.client.force_authenticate(user=self.non_participant_account)
        url = reverse("scene-detail", kwargs={"pk": self.active_private_scene.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_scene_retrieve_private_scene_staff_access(self):
        """Test staff can retrieve private scenes"""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("scene-detail", kwargs={"pk": self.active_private_scene.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK


class PersonaViewPermissionsTestCase(APITestCase):
    """Test persona view permissions based on character ownership"""

    @classmethod
    def setUpTestData(cls):
        cls.participant_account = AccountFactory()
        cls.non_participant_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.scene = SceneFactory()
        cls.participation = SceneParticipationFactory(
            scene=cls.scene,
            account=cls.participant_account,
        )
        cls.staff_participation = SceneParticipationFactory(
            scene=cls.scene,
            account=cls.staff_account,
        )
        cls.persona = _create_owned_persona(cls.participant_account)

    def test_persona_create_participant_permission(self):
        """Test character owner can create personas"""
        # Create identity owned by participant
        identity = CharacterIdentityFactory()
        player_data, _ = PlayerDataFactory._meta.model.objects.get_or_create(
            account=self.participant_account,
        )
        roster_entry = RosterEntryFactory(character=identity.character)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)

        self.client.force_authenticate(user=self.participant_account)
        url = reverse("persona-list")
        data = {
            "character_identity": identity.id,
            "character": identity.character.id,
            "name": "New Persona",
            "description": "Test persona",
        }
        response = self.client.post(
            url,
            json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_201_CREATED

    @suppress_permission_errors
    def test_persona_create_non_participant_denied(self):
        """Test non-owner cannot create personas for characters they don't own"""
        self.client.force_authenticate(user=self.non_participant_account)
        url = reverse("persona-list")
        # Use a character owned by participant, not non_participant
        identity = CharacterIdentityFactory()
        player_data, _ = PlayerDataFactory._meta.model.objects.get_or_create(
            account=self.participant_account,
        )
        roster_entry = RosterEntryFactory(character=identity.character)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)

        data = {
            "character_identity": identity.id,
            "character": identity.character.id,
            "name": "New Persona",
            "description": "Test persona",
        }
        response = self.client.post(
            url,
            json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_persona_create_staff_permission(self):
        """Test staff can create personas for any character"""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("persona-list")
        identity = CharacterIdentityFactory()
        data = {
            "character_identity": identity.id,
            "character": identity.character.id,
            "name": "Staff Persona",
            "description": "Staff test persona",
        }
        response = self.client.post(
            url,
            json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_201_CREATED
