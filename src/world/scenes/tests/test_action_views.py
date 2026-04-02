"""Tests for scene action request and place API endpoints."""

from unittest.mock import MagicMock, patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from actions.constants import ResolutionPhase
from actions.types import PendingActionResolution, StepResult
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterIdentityFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.factories import (
    PlaceFactory,
    SceneActionRequestFactory,
    SceneFactory,
)
from world.scenes.types import EnhancedSceneActionResult


def _make_enhanced_result(action_key: str = "persuade") -> EnhancedSceneActionResult:
    """Build a minimal EnhancedSceneActionResult for mocking."""
    check_result = MagicMock()
    check_result.outcome_name = "Success"
    check_result.success_level = 1
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    action_resolution = PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=45,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )
    return EnhancedSceneActionResult(
        action_resolution=action_resolution,
        action_key=action_key,
    )


class SceneActionRequestViewSetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterIdentityFactory(character=cls.character)
        cls.persona = cls.identity.active_persona

        cls.target_account = AccountFactory()
        cls.target_character = CharacterFactory()
        cls.target_roster_entry = RosterEntryFactory(character=cls.target_character)
        cls.target_player_data = PlayerDataFactory(account=cls.target_account)
        cls.target_tenure = RosterTenureFactory(
            player_data=cls.target_player_data,
            roster_entry=cls.target_roster_entry,
        )
        cls.target_identity = CharacterIdentityFactory(character=cls.target_character)
        cls.target_persona = cls.target_identity.active_persona

        cls.scene = SceneFactory()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_create_action_request(self) -> None:
        url = reverse("sceneactionrequest-list")
        data = {
            "scene": self.scene.pk,
            "target_persona": self.target_persona.pk,
            "action_key": "intimidate",
        }
        response = self.client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["action_key"] == "intimidate"
        assert response.data["status"] == ActionRequestStatus.PENDING

    @patch("world.scenes.action_views.respond_to_action_request")
    def test_respond_accept(self, mock_respond: MagicMock) -> None:
        mock_respond.return_value = _make_enhanced_result("persuade")
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.persona,
            target_persona=self.target_persona,
            action_key="persuade",
        )
        # Authenticate as target
        self.client.force_authenticate(user=self.target_account)
        url = reverse("sceneactionrequest-respond", kwargs={"pk": request.pk})
        response = self.client.post(url, {"decision": ConsentDecision.ACCEPT}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "result" in response.data
        assert response.data["result"]["action_key"] == "persuade"

    def test_respond_deny(self) -> None:
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.persona,
            target_persona=self.target_persona,
            action_key="intimidate",
        )
        self.client.force_authenticate(user=self.target_account)
        url = reverse("sceneactionrequest-respond", kwargs={"pk": request.pk})
        response = self.client.post(url, {"decision": ConsentDecision.DENY}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == ActionRequestStatus.DENIED

    def test_list_own_action_requests(self) -> None:
        SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.persona,
            target_persona=self.target_persona,
        )
        url = reverse("sceneactionrequest-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1


class PlaceViewSetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterIdentityFactory(character=cls.character)
        cls.persona = cls.identity.active_persona
        cls.room = ObjectDBFactory(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_list_places(self) -> None:
        PlaceFactory(room=self.room, name="Bar")
        PlaceFactory(room=self.room, name="Corner")
        url = reverse("place-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_join_place(self) -> None:
        place = PlaceFactory(room=self.room, name="Bar")
        url = reverse("place-join", kwargs={"pk": place.pk})
        response = self.client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["persona"] == self.persona.pk

    def test_leave_place(self) -> None:
        place = PlaceFactory(room=self.room, name="Bar")
        # Join first
        join_url = reverse("place-join", kwargs={"pk": place.pk})
        self.client.post(join_url)

        leave_url = reverse("place-leave", kwargs={"pk": place.pk})
        response = self.client.post(leave_url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_filter_by_room(self) -> None:
        other_room = ObjectDBFactory(
            db_key="Inn",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        PlaceFactory(room=self.room, name="Bar")
        PlaceFactory(room=other_room, name="Lobby")
        url = reverse("place-list")
        response = self.client.get(url, {"room": self.room.pk})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
