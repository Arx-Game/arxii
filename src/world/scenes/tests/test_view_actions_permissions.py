import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.scenes.constants import MessageContext, MessageMode
from world.scenes.factories import (
    PersonaFactory,
    SceneFactory,
    SceneGMParticipationFactory,
    SceneMessageFactory,
    SceneOwnerParticipationFactory,
    SceneParticipationFactory,
)
from world.scenes.models import Scene


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
        cls.active_public_scene = SceneFactory(is_active=True, is_public=True)
        cls.active_private_scene = SceneFactory(is_active=True, is_public=False)
        cls.finished_scene = SceneFactory(is_active=False, is_public=True)
        cls.finished_scene.finish_scene()

        # Set up participations with different roles
        SceneOwnerParticipationFactory(
            scene=cls.active_public_scene, account=cls.owner_account
        )
        SceneGMParticipationFactory(
            scene=cls.active_public_scene, account=cls.gm_account
        )
        SceneParticipationFactory(
            scene=cls.active_public_scene, account=cls.participant_account
        )

        # Set up private scene participations
        SceneOwnerParticipationFactory(
            scene=cls.active_private_scene, account=cls.owner_account
        )
        SceneParticipationFactory(
            scene=cls.active_private_scene, account=cls.participant_account
        )

        # Set up finished scene participations
        SceneOwnerParticipationFactory(
            scene=cls.finished_scene, account=cls.owner_account
        )

    def test_finish_action_owner_permission(self):
        """Test scene owner can finish active scenes"""
        # Create a fresh scene to avoid reusing a finished one
        test_scene = SceneFactory(is_active=True, is_public=True)
        SceneOwnerParticipationFactory(scene=test_scene, account=self.owner_account)

        self.client.force_authenticate(user=self.owner_account)
        url = reverse("scene-finish", kwargs={"pk": test_scene.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        test_scene.refresh_from_db()
        self.assertFalse(test_scene.is_active)
        self.assertIsNotNone(test_scene.date_finished)

    def test_finish_action_gm_permission(self):
        """Test scene GM can finish active scenes"""
        # Create a fresh scene for GM test
        test_scene = SceneFactory(is_active=True, is_public=True)
        SceneGMParticipationFactory(scene=test_scene, account=self.gm_account)

        self.client.force_authenticate(user=self.gm_account)
        url = reverse("scene-finish", kwargs={"pk": test_scene.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_finish_action_staff_permission(self):
        """Test staff can finish any scene"""
        # Create a fresh scene for staff test
        test_scene = SceneFactory(is_active=True, is_public=True)

        self.client.force_authenticate(user=self.staff_account)
        url = reverse("scene-finish", kwargs={"pk": test_scene.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @suppress_permission_errors
    def test_finish_action_participant_denied(self):
        """Test regular participant cannot finish scenes"""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("scene-finish", kwargs={"pk": self.active_public_scene.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @suppress_permission_errors
    def test_finish_action_non_participant_denied(self):
        """Test non-participant cannot finish scenes"""
        self.client.force_authenticate(user=self.non_participant_account)
        url = reverse("scene-finish", kwargs={"pk": self.active_public_scene.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_finish_action_already_finished_scene(self):
        """Test finishing already finished scene returns error"""
        self.client.force_authenticate(user=self.owner_account)
        url = reverse("scene-finish", kwargs={"pk": self.finished_scene.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already finished", response.data["error"])

    def test_scene_update_owner_permission(self):
        """Test scene owner can update scenes"""
        test_scene = SceneFactory(is_active=True, is_public=True)
        SceneOwnerParticipationFactory(scene=test_scene, account=self.owner_account)

        self.client.force_authenticate(user=self.owner_account)
        url = reverse("scene-detail", kwargs={"pk": test_scene.pk})
        data = {"name": "Updated Scene Name", "description": "New description"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        test_scene.refresh_from_db()
        self.assertEqual(test_scene.name, "Updated Scene Name")

    @suppress_permission_errors
    def test_scene_update_gm_denied(self):
        """Test scene GM cannot update scenes (only finish)"""
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("scene-detail", kwargs={"pk": self.active_public_scene.pk})
        data = {"name": "Updated Scene Name"}
        response = self.client.patch(url, data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @suppress_permission_errors
    def test_scene_update_participant_denied(self):
        """Test regular participant cannot update scenes"""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("scene-detail", kwargs={"pk": self.active_public_scene.pk})
        data = {"name": "Updated Scene Name"}
        response = self.client.patch(url, data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_scene_delete_owner_permission(self):
        """Test scene owner can delete scenes"""
        deletable_scene = SceneFactory()
        SceneOwnerParticipationFactory(
            scene=deletable_scene, account=self.owner_account
        )

        self.client.force_authenticate(user=self.owner_account)
        url = reverse("scene-detail", kwargs={"pk": deletable_scene.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Scene.objects.filter(pk=deletable_scene.pk).exists())

    def test_scene_delete_staff_permission(self):
        """Test staff can delete any scene"""
        deletable_scene = SceneFactory()

        self.client.force_authenticate(user=self.staff_account)
        url = reverse("scene-detail", kwargs={"pk": deletable_scene.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_scene_retrieve_private_scene_participant_access(self):
        """Test participant can retrieve private scenes"""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("scene-detail", kwargs={"pk": self.active_private_scene.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.active_private_scene.id)

    @suppress_permission_errors
    def test_scene_retrieve_private_scene_non_participant_denied(self):
        """Test non-participant cannot retrieve private scenes"""
        self.client.force_authenticate(user=self.non_participant_account)
        url = reverse("scene-detail", kwargs={"pk": self.active_private_scene.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_scene_retrieve_private_scene_staff_access(self):
        """Test staff can retrieve private scenes"""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("scene-detail", kwargs={"pk": self.active_private_scene.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PersonaViewPermissionsTestCase(APITestCase):
    """Test persona view permissions for scene participation"""

    @classmethod
    def setUpTestData(cls):
        cls.participant_account = AccountFactory()
        cls.non_participant_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.scene = SceneFactory()
        cls.participation = SceneParticipationFactory(
            scene=cls.scene, account=cls.participant_account
        )
        cls.staff_participation = SceneParticipationFactory(
            scene=cls.scene, account=cls.staff_account
        )
        cls.persona = PersonaFactory(participation=cls.participation)

    def test_persona_create_participant_permission(self):
        """Test scene participant can create personas"""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("persona-list")
        character = CharacterFactory()
        data = {
            "participation": self.participation.id,
            "character": character.id,
            "name": "New Persona",
            "description": "Test persona",
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @suppress_permission_errors
    def test_persona_create_non_participant_denied(self):
        """Test non-participant cannot create personas in scene"""
        self.client.force_authenticate(user=self.non_participant_account)
        url = reverse("persona-list")
        character = CharacterFactory()
        data = {
            "participation": self.participation.id,
            "character": character.id,
            "name": "New Persona",
            "description": "Test persona",
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_persona_create_staff_permission(self):
        """Test staff can create personas in any scene"""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("persona-list")
        character = CharacterFactory()
        data = {
            "participation": self.staff_participation.id,
            "character": character.id,
            "name": "Staff Persona",
            "description": "Staff test persona",
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class SceneMessageViewPermissionsTestCase(APITestCase):
    """Test scene message view permissions and creation"""

    @classmethod
    def setUpTestData(cls):
        cls.sender_account = AccountFactory()
        cls.other_participant_account = AccountFactory()
        cls.non_participant_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.scene = SceneFactory()
        cls.sender_participation = SceneParticipationFactory(
            scene=cls.scene, account=cls.sender_account
        )
        cls.other_participation = SceneParticipationFactory(
            scene=cls.scene, account=cls.other_participant_account
        )

        cls.sender_persona = PersonaFactory(participation=cls.sender_participation)
        cls.other_persona = PersonaFactory(participation=cls.other_participation)

        cls.message = SceneMessageFactory(scene=cls.scene, persona=cls.sender_persona)

    def test_message_create_with_own_persona(self):
        """Test participant can create messages with their own persona"""
        self.client.force_authenticate(user=self.sender_account)
        url = reverse("scenemessage-list")
        data = {
            "persona_id": self.sender_persona.id,
            "content": "Test message content",
            "context": MessageContext.PUBLIC,
            "mode": MessageMode.POSE,
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @suppress_permission_errors
    def test_message_create_with_other_persona_denied(self):
        """Test participant cannot create messages with other participant's persona"""
        self.client.force_authenticate(user=self.sender_account)
        url = reverse("scenemessage-list")
        data = {
            "persona_id": self.other_persona.id,  # Not owned by sender_account
            "content": "Test message content",
            "context": MessageContext.PUBLIC,
            "mode": MessageMode.POSE,
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_message_update_sender_permission(self):
        """Test message sender can update their own messages"""
        self.client.force_authenticate(user=self.sender_account)
        url = reverse("scenemessage-detail", kwargs={"pk": self.message.pk})
        data = {"content": "Updated message content"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.message.refresh_from_db()
        self.assertEqual(self.message.content, "Updated message content")

    @suppress_permission_errors
    def test_message_update_other_participant_denied(self):
        """Test other participant cannot update messages they didn't send"""
        self.client.force_authenticate(user=self.other_participant_account)
        url = reverse("scenemessage-detail", kwargs={"pk": self.message.pk})
        data = {"content": "Unauthorized update"}
        response = self.client.patch(url, data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_message_update_staff_permission(self):
        """Test staff can update any message"""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("scenemessage-detail", kwargs={"pk": self.message.pk})
        data = {"content": "Staff updated content"}
        response = self.client.patch(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_message_delete_sender_permission(self):
        """Test message sender can delete their own messages"""
        deletable_message = SceneMessageFactory(
            scene=self.scene, persona=self.sender_persona
        )

        self.client.force_authenticate(user=self.sender_account)
        url = reverse("scenemessage-detail", kwargs={"pk": deletable_message.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    @suppress_permission_errors
    def test_message_delete_other_participant_denied(self):
        """Test other participant cannot delete messages they didn't send"""
        self.client.force_authenticate(user=self.other_participant_account)
        url = reverse("scenemessage-detail", kwargs={"pk": self.message.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
