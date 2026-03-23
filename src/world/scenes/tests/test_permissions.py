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


class ScenePermissionsTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Create test accounts - expensive Evennia account creation happens once
        cls.owner = AccountFactory(username="owner")
        cls.gm = AccountFactory(username="gm")
        cls.participant = AccountFactory(username="participant")
        cls.outsider = AccountFactory(username="outsider")
        cls.staff = AccountFactory(username="staff", is_staff=True)

        # Create scene with different participation levels
        cls.scene = SceneFactory()
        SceneOwnerParticipationFactory(scene=cls.scene, account=cls.owner)
        SceneGMParticipationFactory(scene=cls.scene, account=cls.gm)
        SceneParticipationFactory(scene=cls.scene, account=cls.participant)

    def test_scene_list_public_access(self):
        """Anyone can list public scenes"""
        # Unauthenticated user
        url = reverse("scene-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_scene_detail_public_access(self):
        """Anyone can view public scene details"""
        url = reverse("scene-detail", kwargs={"pk": self.scene.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_scene_detail_private_access(self):
        """Only participants can view private scenes"""
        private_scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        SceneParticipationFactory(scene=private_scene, account=self.participant)

        url = reverse("scene-detail", kwargs={"pk": private_scene.pk})

        # Outsider cannot access
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Participant can access
        self.client.force_authenticate(user=self.participant)
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_scene_modify_owner_permission(self):
        """Only scene owners can modify scenes"""
        url = reverse("scene-detail", kwargs={"pk": self.scene.pk})
        data = {"name": "Updated Scene Name"}

        # Outsider cannot modify
        self.client.force_authenticate(user=self.outsider)
        response = self.client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Participant cannot modify
        self.client.force_authenticate(user=self.participant)
        response = self.client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # GM cannot modify (only finish)
        self.client.force_authenticate(user=self.gm)
        response = self.client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Owner can modify
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_scene_modify_staff_permission(self):
        """Staff can always modify scenes"""
        url = reverse("scene-detail", kwargs={"pk": self.scene.pk})
        data = {"name": "Staff Updated Scene"}

        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_scene_finish_permission(self):
        """Scene owners and staff can finish scenes"""
        url = reverse("scene-finish", kwargs={"pk": self.scene.pk})

        # Outsider cannot finish
        self.client.force_authenticate(user=self.outsider)
        response = self.client.post(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Participant cannot finish
        self.client.force_authenticate(user=self.participant)
        response = self.client.post(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Owner can finish
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_scene_delete_permission(self):
        """Only scene owners and staff can delete scenes"""
        scene_to_delete = SceneFactory()
        SceneOwnerParticipationFactory(scene=scene_to_delete, account=self.owner)

        url = reverse("scene-detail", kwargs={"pk": scene_to_delete.pk})

        # Outsider cannot delete
        self.client.force_authenticate(user=self.outsider)
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Owner can delete
        self.client.force_authenticate(user=self.owner)
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT


class PersonaPermissionsTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.participant = AccountFactory(username="participant")
        cls.outsider = AccountFactory(username="outsider")
        cls.staff = AccountFactory(username="staff", is_staff=True)

        cls.scene = SceneFactory()
        cls.participation = SceneParticipationFactory(
            scene=cls.scene,
            account=cls.participant,
        )
        cls.persona = _create_owned_persona(cls.participant)

    @suppress_permission_errors
    def test_create_persona_participant_only(self):
        """Only scene participants can create personas"""
        # Create identity owned by participant
        identity = CharacterIdentityFactory()
        player_data, _ = PlayerDataFactory._meta.model.objects.get_or_create(
            account=self.participant,
        )
        roster_entry = RosterEntryFactory(character=identity.character)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)

        url = reverse("persona-list")
        data = {
            "name": "Test Persona",
            "character_identity": identity.id,
            "character": identity.character.id,
        }

        # Outsider cannot create persona (doesn't own the character)
        self.client.force_authenticate(user=self.outsider)
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Participant can create persona (owns the character)
        self.client.force_authenticate(user=self.participant)
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    @suppress_permission_errors
    def test_modify_persona_participant_permission(self):
        """Only character owners and staff can modify personas"""
        url = reverse("persona-detail", kwargs={"pk": self.persona.pk})
        data = {"name": "Updated Persona"}

        # Outsider cannot modify
        self.client.force_authenticate(user=self.outsider)
        response = self.client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Character owner can modify
        self.client.force_authenticate(user=self.participant)
        response = self.client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Staff can modify
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK


class SceneCreationPermissionsTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory(username="user")
        cls.staff = AccountFactory(username="staff", is_staff=True)

    @suppress_permission_errors
    def test_scene_creation_authenticated_only(self):
        """Only authenticated users can create scenes"""
        url = reverse("scene-list")
        data = {"name": "New Scene"}

        # Unauthenticated cannot create
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Authenticated user can create
        self.client.force_authenticate(user=self.user)
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Staff can create
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
