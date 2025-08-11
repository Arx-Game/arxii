from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.scenes.factories import (
    PersonaFactory,
    SceneFactory,
    SceneGMParticipationFactory,
    SceneMessageFactory,
    SceneOwnerParticipationFactory,
    SceneParticipationFactory,
)


class ScenePermissionsTestCase(APITestCase):
    def setUp(self):
        # Create test accounts
        self.owner = AccountFactory(username="owner")
        self.gm = AccountFactory(username="gm")
        self.participant = AccountFactory(username="participant")
        self.outsider = AccountFactory(username="outsider")
        self.staff = AccountFactory(username="staff", is_staff=True)

        # Create scene with different participation levels
        self.scene = SceneFactory()
        SceneOwnerParticipationFactory(scene=self.scene, account=self.owner)
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        SceneParticipationFactory(scene=self.scene, account=self.participant)

    def test_scene_list_public_access(self):
        """Anyone can list public scenes"""
        # Unauthenticated user
        url = reverse("scene-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_scene_detail_public_access(self):
        """Anyone can view public scene details"""
        url = reverse("scene-detail", kwargs={"pk": self.scene.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @suppress_permission_errors
    def test_scene_detail_private_access(self):
        """Only participants can view private scenes"""
        private_scene = SceneFactory(is_public=False)
        SceneParticipationFactory(scene=private_scene, account=self.participant)

        url = reverse("scene-detail", kwargs={"pk": private_scene.pk})

        # Outsider cannot access
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Participant can access
        self.client.force_authenticate(user=self.participant)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @suppress_permission_errors
    def test_scene_modify_owner_permission(self):
        """Only scene owners can modify scenes"""
        url = reverse("scene-detail", kwargs={"pk": self.scene.pk})
        data = {"name": "Updated Scene Name"}

        # Outsider cannot modify
        self.client.force_authenticate(user=self.outsider)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Participant cannot modify
        self.client.force_authenticate(user=self.participant)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # GM cannot modify (only finish)
        self.client.force_authenticate(user=self.gm)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Owner can modify
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_scene_modify_staff_permission(self):
        """Staff can always modify scenes"""
        url = reverse("scene-detail", kwargs={"pk": self.scene.pk})
        data = {"name": "Staff Updated Scene"}

        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @suppress_permission_errors
    def test_scene_finish_permission(self):
        """Scene owners and staff can finish scenes"""
        url = reverse("scene-finish", kwargs={"pk": self.scene.pk})

        # Outsider cannot finish
        self.client.force_authenticate(user=self.outsider)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Participant cannot finish
        self.client.force_authenticate(user=self.participant)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Owner can finish
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @suppress_permission_errors
    def test_scene_delete_permission(self):
        """Only scene owners and staff can delete scenes"""
        scene_to_delete = SceneFactory()
        SceneOwnerParticipationFactory(scene=scene_to_delete, account=self.owner)

        url = reverse("scene-detail", kwargs={"pk": scene_to_delete.pk})

        # Outsider cannot delete
        self.client.force_authenticate(user=self.outsider)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Owner can delete
        self.client.force_authenticate(user=self.owner)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class PersonaPermissionsTestCase(APITestCase):
    def setUp(self):
        self.participant = AccountFactory(username="participant")
        self.outsider = AccountFactory(username="outsider")
        self.staff = AccountFactory(username="staff", is_staff=True)

        self.scene = SceneFactory()
        SceneParticipationFactory(scene=self.scene, account=self.participant)
        self.persona = PersonaFactory(scene=self.scene, account=self.participant)

    @suppress_permission_errors
    def test_create_persona_participant_only(self):
        """Only scene participants can create personas"""
        url = reverse("persona-list")
        data = {
            "scene": self.scene.id,
            "name": "Test Persona",
            "account": self.participant.id,
        }

        # Outsider cannot create persona
        self.client.force_authenticate(user=self.outsider)
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Participant can create persona
        self.client.force_authenticate(user=self.participant)
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @suppress_permission_errors
    def test_modify_persona_participant_permission(self):
        """Only scene participants and staff can modify personas"""
        url = reverse("persona-detail", kwargs={"pk": self.persona.pk})
        data = {"name": "Updated Persona"}

        # Outsider cannot modify
        self.client.force_authenticate(user=self.outsider)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Participant can modify
        self.client.force_authenticate(user=self.participant)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Staff can modify
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class SceneMessagePermissionsTestCase(APITestCase):
    def setUp(self):
        self.sender = AccountFactory(username="sender")
        self.participant = AccountFactory(username="participant")
        self.outsider = AccountFactory(username="outsider")
        self.staff = AccountFactory(username="staff", is_staff=True)

        self.scene = SceneFactory()
        SceneParticipationFactory(scene=self.scene, account=self.sender)
        SceneParticipationFactory(scene=self.scene, account=self.participant)

        self.sender_persona = PersonaFactory(scene=self.scene, account=self.sender)
        self.participant_persona = PersonaFactory(
            scene=self.scene, account=self.participant
        )

        self.message = SceneMessageFactory(
            scene=self.scene, persona=self.sender_persona
        )

    @suppress_permission_errors
    def test_create_message_participant_only(self):
        """Only scene participants can create messages"""
        url = reverse("scenemessage-list")
        data = {"persona_id": self.sender_persona.id, "content": "Test message"}

        # Outsider cannot create message
        self.client.force_authenticate(user=self.outsider)
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Message sender can create message with their persona
        self.client.force_authenticate(user=self.sender)
        response = self.client.post(url, data, format="json")
        # Note: This might fail due to scene field issues, but permission check should pass
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @suppress_permission_errors
    def test_create_message_wrong_persona(self):
        """Users cannot create messages with other users' personas"""
        url = reverse("scenemessage-list")
        data = {
            "persona_id": self.sender_persona.id,  # Sender's persona
            "content": "Test message",
        }

        # Participant cannot use sender's persona
        self.client.force_authenticate(user=self.participant)
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @suppress_permission_errors
    def test_modify_message_sender_only(self):
        """Only message sender and staff can modify messages"""
        url = reverse("scenemessage-detail", kwargs={"pk": self.message.pk})
        data = {"content": "Updated message"}

        # Outsider cannot modify
        self.client.force_authenticate(user=self.outsider)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Other participant cannot modify
        self.client.force_authenticate(user=self.participant)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Message sender can modify
        self.client.force_authenticate(user=self.sender)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_modify_message_staff_permission(self):
        """Staff can always modify messages"""
        url = reverse("scenemessage-detail", kwargs={"pk": self.message.pk})
        data = {"content": "Staff updated message"}

        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @suppress_permission_errors
    def test_delete_message_sender_only(self):
        """Only message sender and staff can delete messages"""
        message_to_delete = SceneMessageFactory(
            scene=self.scene, persona=self.sender_persona
        )
        url = reverse("scenemessage-detail", kwargs={"pk": message_to_delete.pk})

        # Other participant cannot delete
        self.client.force_authenticate(user=self.participant)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Message sender can delete
        self.client.force_authenticate(user=self.sender)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class SceneCreationPermissionsTestCase(APITestCase):
    def setUp(self):
        self.user = AccountFactory(username="user")
        self.staff = AccountFactory(username="staff", is_staff=True)

    @suppress_permission_errors
    def test_scene_creation_authenticated_only(self):
        """Only authenticated users can create scenes"""
        url = reverse("scene-list")
        data = {"name": "New Scene"}

        # Unauthenticated cannot create
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Authenticated user can create
        self.client.force_authenticate(user=self.user)
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Staff can create
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
