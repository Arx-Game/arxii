"""Tests for SceneSummaryRevision API."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterIdentityFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import ScenePrivacyMode, SummaryAction
from world.scenes.factories import PersonaFactory, SceneFactory, SceneParticipationFactory
from world.scenes.models import SceneSummaryRevision


def _create_owned_persona(account, **persona_kwargs):
    """Create a Persona whose character is owned by the given account via RosterTenure."""
    identity = CharacterIdentityFactory()
    player_data, _ = PlayerDataFactory._meta.model.objects.get_or_create(account=account)
    roster_entry = RosterEntryFactory(character_sheet__character=identity.character)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    if persona_kwargs:
        return PersonaFactory(
            character_sheet=identity.character.sheet_data,
            **persona_kwargs,
        )
    return identity.active_persona


class SceneSummaryRevisionViewSetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.identity = CharacterIdentityFactory()

        cls.other_account = AccountFactory()
        cls.other_identity = CharacterIdentityFactory()

        # Ephemeral scene with participant
        cls.ephemeral_scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        cls.participation = SceneParticipationFactory(
            scene=cls.ephemeral_scene,
            account=cls.account,
        )
        cls.persona = _create_owned_persona(cls.account)

        # Public (non-ephemeral) scene
        cls.public_scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.public_participation = SceneParticipationFactory(
            scene=cls.public_scene,
            account=cls.account,
        )
        cls.public_persona = _create_owned_persona(cls.account)

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_participant_can_submit_summary_for_ephemeral_scene(self) -> None:
        """Participant can submit a summary revision for an ephemeral scene."""
        url = reverse("scenesummaryrevision-list")
        data = {
            "scene": self.ephemeral_scene.pk,
            "persona": self.persona.pk,
            "content": "A summary of what happened in the scene.",
            "action": SummaryAction.SUBMIT,
        }
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert SceneSummaryRevision.objects.filter(
            scene=self.ephemeral_scene,
            persona=self.persona,
        ).exists()
        assert response.data["persona_name"] == self.persona.name

    def test_cannot_submit_summary_for_non_ephemeral_scene(self) -> None:
        """Summary revisions cannot be submitted for non-ephemeral scenes."""
        url = reverse("scenesummaryrevision-list")
        data = {
            "scene": self.public_scene.pk,
            "persona": self.public_persona.pk,
            "content": "Attempted summary.",
            "action": SummaryAction.SUBMIT,
        }
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "scene" in response.data

    def test_non_participant_cannot_submit_summary(self) -> None:
        """A non-participant cannot submit a summary revision."""
        self.client.force_authenticate(user=self.other_account)

        # Create a persona for other_account that is NOT in the ephemeral scene
        other_scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        SceneParticipationFactory(
            scene=other_scene,
            account=self.other_account,
        )
        other_persona = PersonaFactory()

        url = reverse("scenesummaryrevision-list")
        data = {
            "scene": self.ephemeral_scene.pk,
            "persona": other_persona.pk,
            "content": "Attempted summary from non-participant.",
            "action": SummaryAction.SUBMIT,
        }
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "persona" in response.data

    def test_list_only_shows_participated_scenes(self) -> None:
        """List endpoint only shows revisions for scenes the user participates in."""
        # Create a revision in the user's scene
        SceneSummaryRevision.objects.create(
            scene=self.ephemeral_scene,
            persona=self.persona,
            content="My revision",
            action=SummaryAction.SUBMIT,
        )

        # Create a revision in another scene the user is NOT in
        other_scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        SceneParticipationFactory(
            scene=other_scene,
            account=self.other_account,
        )
        other_persona = PersonaFactory()
        SceneSummaryRevision.objects.create(
            scene=other_scene,
            persona=other_persona,
            content="Other revision",
            action=SummaryAction.SUBMIT,
        )

        url = reverse("scenesummaryrevision-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["content"] == "My revision"
