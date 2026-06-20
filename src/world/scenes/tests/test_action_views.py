"""Tests for scene action request and place API endpoints."""

from unittest.mock import MagicMock, patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from actions.types import TargetType
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterStatus
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueFactory,
)
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_models import (
    SceneActionRequest,
    SceneActionTarget,
    SceneCastPullDeclaration,
)
from world.scenes.factories import (
    PlaceFactory,
    SceneActionRequestFactory,
    SceneActionTargetFactory,
    SceneFactory,
)
from world.scenes.tests.cast_test_helpers import (
    make_cast_pull_fixture,
    make_castable_technique,
    make_enhanced_result as _make_enhanced_result,
)


class SceneActionRequestViewSetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.identity.primary_persona

        cls.target_account = AccountFactory()
        cls.target_character = CharacterFactory()
        cls.target_roster_entry = RosterEntryFactory(
            character_sheet__character=cls.target_character
        )
        cls.target_player_data = PlayerDataFactory(account=cls.target_account)
        cls.target_tenure = RosterTenureFactory(
            player_data=cls.target_player_data,
            roster_entry=cls.target_roster_entry,
        )
        cls.target_identity = CharacterSheetFactory(character=cls.target_character)
        cls.target_persona = cls.target_identity.primary_persona

        cls.scene = SceneFactory()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_create_action_request(self) -> None:
        url = reverse("sceneactionrequest-list")
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
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


def _make_area_action_mock() -> MagicMock:
    """Return a mock action object with target_type = AREA."""
    mock = MagicMock()
    mock.target_type = TargetType.AREA
    return mock


def _make_single_action_mock() -> MagicMock:
    """Return a mock action object with target_type = SINGLE."""
    mock = MagicMock()
    mock.target_type = TargetType.SINGLE
    return mock


def _make_self_action_mock() -> MagicMock:
    """Return a mock action object with target_type = SELF."""
    mock = MagicMock()
    mock.target_type = TargetType.SELF
    return mock


def _make_filtered_group_action_mock() -> MagicMock:
    """Return a mock action object with target_type = FILTERED_GROUP."""
    mock = MagicMock()
    mock.target_type = TargetType.FILTERED_GROUP
    return mock


class MultiTargetDispatchTestCase(APITestCase):
    """Tests for multi-target dispatch via target_persona_ids (#572 Task 4)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.identity.primary_persona

        cls.target_account = AccountFactory()
        cls.target_character = CharacterFactory()
        cls.target_roster_entry = RosterEntryFactory(
            character_sheet__character=cls.target_character
        )
        cls.target_player_data = PlayerDataFactory(account=cls.target_account)
        cls.target_tenure = RosterTenureFactory(
            player_data=cls.target_player_data,
            roster_entry=cls.target_roster_entry,
        )
        cls.target_identity = CharacterSheetFactory(character=cls.target_character)
        cls.target_persona = cls.target_identity.primary_persona

        cls.extra_account = AccountFactory()
        cls.extra_character = CharacterFactory()
        cls.extra_roster_entry = RosterEntryFactory(character_sheet__character=cls.extra_character)
        cls.extra_player_data = PlayerDataFactory(account=cls.extra_account)
        cls.extra_tenure = RosterTenureFactory(
            player_data=cls.extra_player_data,
            roster_entry=cls.extra_roster_entry,
        )
        cls.extra_identity = CharacterSheetFactory(character=cls.extra_character)
        cls.extra_persona = cls.extra_identity.primary_persona

        cls.extra2_account = AccountFactory()
        cls.extra2_character = CharacterFactory()
        cls.extra2_roster_entry = RosterEntryFactory(
            character_sheet__character=cls.extra2_character
        )
        cls.extra2_player_data = PlayerDataFactory(account=cls.extra2_account)
        cls.extra2_tenure = RosterTenureFactory(
            player_data=cls.extra2_player_data,
            roster_entry=cls.extra2_roster_entry,
        )
        cls.extra2_identity = CharacterSheetFactory(character=cls.extra2_character)
        cls.extra2_persona = cls.extra2_identity.primary_persona

        cls.scene = SceneFactory()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)
        self.url = reverse("sceneactionrequest-list")

    @patch("world.scenes.action_services._auto_resolve_npc_targets")
    @patch("world.scenes.action_views.get_action")
    def test_area_action_with_three_ids_creates_primary_and_two_additional_rows(
        self, mock_get_action: MagicMock, mock_auto_resolve: MagicMock
    ) -> None:
        """An AREA action with 3 ids creates 1 primary FK + 2 SceneActionTarget rows."""
        mock_get_action.return_value = _make_area_action_mock()
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "target_persona_ids": [
                self.target_persona.pk,
                self.extra_persona.pk,
                self.extra2_persona.pk,
            ],
            "action_key": "test_area_action",
        }
        before_count = SceneActionRequest.objects.count()
        response = self.client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data

        # One new SceneActionRequest row
        assert SceneActionRequest.objects.count() == before_count + 1
        request_id = response.data["id"]
        action_request = SceneActionRequest.objects.get(pk=request_id)

        # Primary target is on the FK
        assert action_request.target_persona_id == self.target_persona.pk

        # Two additional SceneActionTarget rows
        additional = SceneActionTarget.objects.filter(action_request=action_request)
        assert additional.count() == 2
        additional_ids = set(additional.values_list("target_persona_id", flat=True))
        assert self.extra_persona.pk in additional_ids
        assert self.extra2_persona.pk in additional_ids

        # _auto_resolve_npc_targets called exactly once (multi-target path)
        mock_auto_resolve.assert_called_once()

    @patch("world.scenes.action_views.get_action")
    def test_single_action_rejects_more_than_one_target_id(
        self, mock_get_action: MagicMock
    ) -> None:
        """A SINGLE action with >1 target_persona_ids returns 400."""
        mock_get_action.return_value = _make_single_action_mock()
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "target_persona_ids": [self.target_persona.pk, self.extra_persona.pk],
            "action_key": "intimidate",
        }
        response = self.client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "target_persona_ids" in response.data

    def test_disagreeing_target_persona_and_target_persona_ids_returns_400(self) -> None:
        """Sending target_persona != target_persona_ids[0] returns 400 from the serializer."""
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "target_persona": self.extra_persona.pk,
            "target_persona_ids": [self.target_persona.pk],
            "action_key": "intimidate",
        }
        response = self.client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "target_persona" in response.data

    @patch("world.scenes.action_services._auto_resolve_npc_targets")
    @patch("world.scenes.action_views.get_action")
    def test_duplicate_ids_are_deduped(
        self, mock_get_action: MagicMock, mock_auto_resolve: MagicMock
    ) -> None:
        """Duplicate ids in target_persona_ids are silently deduped; only unique targets created."""
        mock_get_action.return_value = _make_area_action_mock()
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "target_persona_ids": [
                self.target_persona.pk,
                self.extra_persona.pk,
                self.extra_persona.pk,  # duplicate
            ],
            "action_key": "test_area_action",
        }
        response = self.client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        request_id = response.data["id"]
        action_request = SceneActionRequest.objects.get(pk=request_id)
        # Primary = target_persona, additional = 1 row for extra_persona (deduped)
        assert action_request.target_persona_id == self.target_persona.pk
        additional = SceneActionTarget.objects.filter(action_request=action_request)
        assert additional.count() == 1
        assert additional.first().target_persona_id == self.extra_persona.pk

    def test_existing_single_target_path_unchanged(self) -> None:
        """Existing single-target dispatch (target_persona only) still works."""
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "target_persona": self.target_persona.pk,
            "action_key": "intimidate",
        }
        response = self.client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["action_key"] == "intimidate"
        assert response.data["status"] == ActionRequestStatus.PENDING

    @patch("world.scenes.action_views.get_action")
    def test_self_action_rejects_any_target_ids(self, mock_get_action: MagicMock) -> None:
        """A SELF action with any target_persona_ids returns 400."""
        mock_get_action.return_value = _make_self_action_mock()
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "target_persona_ids": [self.target_persona.pk],
            "action_key": "self_action",
        }
        response = self.client.post(self.url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "target_persona_ids" in response.data

    @patch("world.scenes.action_services._auto_resolve_npc_targets")
    @patch("world.scenes.action_views.get_action")
    def test_filtered_group_requires_at_least_one_id(
        self, mock_get_action: MagicMock, mock_auto_resolve: MagicMock
    ) -> None:
        """A FILTERED_GROUP action with no ids returns 400; with a list it succeeds."""
        mock_get_action.return_value = _make_filtered_group_action_mock()

        # No ids → 400.
        data_empty = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "target_persona_ids": [],
            "action_key": "group_action",
        }
        response_empty = self.client.post(self.url, data_empty, format="json")
        assert response_empty.status_code == status.HTTP_400_BAD_REQUEST
        assert "target_persona_ids" in response_empty.data

        # Providing ids → 201.
        data_with_ids = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "target_persona_ids": [self.target_persona.pk, self.extra_persona.pk],
            "action_key": "group_action",
        }
        response_ok = self.client.post(self.url, data_with_ids, format="json")
        assert response_ok.status_code == status.HTTP_201_CREATED, response_ok.data


class PlaceViewSetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.identity.primary_persona
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


class CastEndpointTestCase(APITestCase):
    """Tests for POST /api/action-requests/cast/."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia import create_object

        from world.traits.factories import CheckSystemSetupFactory
        from world.vitals.models import CharacterVitals

        CheckSystemSetupFactory.create()
        room = create_object("typeclasses.rooms.Room", key="Cast Room API", nohome=True)
        cls.scene = SceneFactory(location=room)

        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.identity.primary_persona

        CharacterAnimaFactory(character=cls.character, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=cls.identity,
            health=50,
            max_health=50,
            base_max_health=50,
        )

        cls.target_account = AccountFactory()
        cls.target_character = CharacterFactory()
        cls.target_roster_entry = RosterEntryFactory(
            character_sheet__character=cls.target_character
        )
        cls.target_player_data = PlayerDataFactory(account=cls.target_account)
        cls.target_tenure = RosterTenureFactory(
            player_data=cls.target_player_data,
            roster_entry=cls.target_roster_entry,
        )
        cls.target_identity = CharacterSheetFactory(character=cls.target_character)
        cls.target_persona = cls.target_identity.primary_persona
        CharacterVitals.objects.create(
            character_sheet=cls.target_identity,
            health=50,
            max_health=50,
            base_max_health=50,
        )

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    def _cast_url(self) -> str:
        return reverse("sceneactionrequest-cast")

    def test_immediate_cast_resolves_and_returns_result(self) -> None:
        """Self-cast (no target) resolves immediately; response includes result."""
        technique = make_castable_technique()
        CharacterTechniqueFactory(character=self.identity, technique=technique)
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == ActionRequestStatus.RESOLVED
        assert "result" in response.data
        assert response.data["result"]["action_key"] == "cast"
        assert "encounter" not in response.data

    def test_immediate_cast_power_ledger_in_result(self) -> None:
        """Immediate cast includes power_ledger in the result payload."""
        technique = make_castable_technique()
        CharacterTechniqueFactory(character=self.identity, technique=technique)
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        # power_ledger may be None if no environment modifiers are present, but
        # the key must be present in the result payload.
        assert "power_ledger" in response.data["result"]

    def test_benign_cast_at_other_pc_is_pending(self) -> None:
        """Benign cast at another PC returns PENDING request (consent flow)."""
        technique = make_castable_technique(hostile=False)
        CharacterTechniqueFactory(character=self.identity, technique=technique)
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
            "target_persona": self.target_persona.pk,
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == ActionRequestStatus.PENDING
        assert "result" not in response.data

    def test_cast_unknown_technique_returns_400(self) -> None:
        """Casting a technique the initiator does not know → 400."""
        technique = make_castable_technique()
        # Do NOT grant the technique to the persona
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cast_wrong_persona_returns_400(self) -> None:
        """Using a persona belonging to a different account → 400."""
        technique = make_castable_technique()
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.target_persona.pk,
            "technique_id": technique.pk,
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cast_missing_scene_returns_404(self) -> None:
        """Non-existent (or inactive) scene id → 404."""
        technique = make_castable_technique()
        CharacterTechniqueFactory(character=self.identity, technique=technique)
        data = {
            "scene": 999999,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_cast_returns_403(self) -> None:
        """Unauthenticated request → 403 (session auth returns forbidden, not 401)."""
        self.client.force_authenticate(user=None)
        technique = make_castable_technique()
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_hostile_cast_at_other_pc_returns_201_with_encounter(self) -> None:
        """Hostile cast at another PC → 201, response contains an encounter in DECLARING status."""
        technique = make_castable_technique(hostile=True)
        CharacterTechniqueFactory(character=self.identity, technique=technique)
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
            "target_persona": self.target_persona.pk,
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert "encounter" in response.data
        encounter_data = response.data["encounter"]
        assert encounter_data["status"] == EncounterStatus.DECLARING

    def test_cast_technique_without_action_template_returns_400(self) -> None:
        """Casting a known technique that has no action_template → 400 (not castable standalone)."""
        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            # action_template intentionally omitted → None
        )
        CharacterTechniqueFactory(character=self.identity, technique=technique)
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_accept_path_result_carries_power_ledger_key(self) -> None:
        """On consent accept, the respond endpoint surfaces power_ledger in the result.

        We test this at the API layer: a benign cast at another PC creates a PENDING
        request; the target accepts via the respond endpoint; the result dict in the
        response contains a power_ledger key (may be None if no env modifiers, but
        the key must be present, proving the accept path now reads from the result
        object rather than being silently absent).
        """
        technique = make_castable_technique(hostile=False)
        CharacterTechniqueFactory(character=self.identity, technique=technique)

        # Create a pending cast request via the cast endpoint
        cast_data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
            "target_persona": self.target_persona.pk,
        }
        cast_response = self.client.post(self._cast_url(), cast_data, format="json")
        assert cast_response.status_code == status.HTTP_201_CREATED
        assert cast_response.data["status"] == ActionRequestStatus.PENDING
        request_pk = cast_response.data["id"]

        # Target accepts
        self.client.force_authenticate(user=self.target_account)
        respond_url = reverse("sceneactionrequest-respond", kwargs={"pk": request_pk})
        respond_response = self.client.post(
            respond_url, {"decision": ConsentDecision.ACCEPT}, format="json"
        )
        assert respond_response.status_code == status.HTTP_200_OK
        assert "result" in respond_response.data
        # power_ledger key must be present (value may be None for benign casts
        # without environment modifiers, but the field must not be silently absent)
        assert "power_ledger" in respond_response.data["result"]

    # ------------------------------------------------------------------
    # Pull-declaration tests (#854)
    # ------------------------------------------------------------------

    _PULL_TIER = 2
    _PULL_RESONANCE_COST = 3
    _STARTING_BALANCE = 10

    def _make_pull_fixture(self, *, hostile: bool = False):
        """Build a TECHNIQUE-anchored thread, resonance balance, and pull tier cost.

        Returns (technique, character_resonance, resonance, thread) so the
        caller can compose the POST payload and verify balance changes.
        Fresh rows per test — balance mutations must not leak via the identity map.
        """
        technique, character_resonance, resonance, thread = make_cast_pull_fixture(
            self.identity,
            hostile=hostile,
            tier=self._PULL_TIER,
            resonance_cost=self._PULL_RESONANCE_COST,
            starting_balance=self._STARTING_BALANCE,
        )
        CharacterTechniqueFactory(character=self.identity, technique=technique)
        return technique, character_resonance, resonance, thread

    def test_immediate_cast_with_pull_charges_and_succeeds(self) -> None:
        """POST with pull declaration on a self-cast → 201 RESOLVED; balance debited."""
        technique, character_resonance, resonance, thread = self._make_pull_fixture()
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
            "pull": {
                "resonance_id": resonance.pk,
                "tier": self._PULL_TIER,
                "thread_ids": [thread.pk],
            },
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == ActionRequestStatus.RESOLVED
        character_resonance.refresh_from_db()
        assert character_resonance.balance == self._STARTING_BALANCE - self._PULL_RESONANCE_COST

    def test_cast_pull_unaffordable_returns_400(self) -> None:
        """Zero balance on a pull attempt → 400; no new RESOLVED request row created."""
        technique, character_resonance, resonance, thread = self._make_pull_fixture()
        character_resonance.balance = 0
        character_resonance.save(update_fields=["balance"])

        before_count = SceneActionRequest.objects.count()
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
            "pull": {
                "resonance_id": resonance.pk,
                "tier": self._PULL_TIER,
                "thread_ids": [thread.pk],
            },
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # The whole cast rolled back — no new request rows.
        assert SceneActionRequest.objects.count() == before_count

    def test_hostile_cast_with_pull_rejected(self) -> None:
        """Declaring a pull on a hostile cast → 400; 'pull' key in the error payload."""
        technique, _cr, resonance, thread = self._make_pull_fixture(hostile=True)
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
            "target_persona": self.target_persona.pk,
            "pull": {
                "resonance_id": resonance.pk,
                "tier": self._PULL_TIER,
                "thread_ids": [thread.pk],
            },
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "pull" in response.data

    def test_benign_cast_with_pull_creates_declaration(self) -> None:
        """Benign cast at another PC with pull returns PENDING; pull declaration row created."""
        technique, character_resonance, resonance, thread = self._make_pull_fixture()
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
            "target_persona": self.target_persona.pk,
            "pull": {
                "resonance_id": resonance.pk,
                "tier": self._PULL_TIER,
                "thread_ids": [thread.pk],
            },
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == ActionRequestStatus.PENDING
        request_id = response.data["id"]
        assert SceneCastPullDeclaration.objects.filter(request_id=request_id).exists()
        character_resonance.refresh_from_db()
        assert character_resonance.balance == self._STARTING_BALANCE

    def test_cast_response_includes_action_interaction(self) -> None:
        """Immediate cast response exposes action_interaction as the FK integer."""
        technique = make_castable_technique()
        CharacterTechniqueFactory(character=self.identity, technique=technique)
        data = {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": technique.pk,
        }
        response = self.client.post(self._cast_url(), data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert "action_interaction" in response.data
        assert response.data["action_interaction"] is not None
        request_id = response.data["id"]
        db_request = SceneActionRequest.objects.get(pk=request_id)
        assert response.data["action_interaction"] == db_request.action_interaction_id


class CastableTechniquesEndpointTestCase(APITestCase):
    """Tests for GET /api/action-requests/castable-techniques/."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.identity.primary_persona

        cls.other_account = AccountFactory()
        cls.other_character = CharacterFactory()
        cls.other_roster_entry = RosterEntryFactory(character_sheet__character=cls.other_character)
        cls.other_player_data = PlayerDataFactory(account=cls.other_account)
        cls.other_tenure = RosterTenureFactory(
            player_data=cls.other_player_data,
            roster_entry=cls.other_roster_entry,
        )
        cls.other_identity = CharacterSheetFactory(character=cls.other_character)
        cls.other_persona = cls.other_identity.primary_persona

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def _url(self) -> str:
        return reverse("sceneactionrequest-castable-techniques")

    def test_returns_only_castable_techniques(self) -> None:
        """Only techniques with action_template (castable standalone) are returned."""
        castable = make_castable_technique()
        non_castable = TechniqueFactory(effect_type=BinaryEffectTypeFactory(), damage_profile=False)
        CharacterTechniqueFactory(character=self.identity, technique=castable)
        CharacterTechniqueFactory(character=self.identity, technique=non_castable)
        response = self.client.get(self._url(), {"initiator_persona": self.persona.pk})
        assert response.status_code == status.HTTP_200_OK
        ids = [t["id"] for t in response.data]
        assert castable.pk in ids
        assert non_castable.pk not in ids

    def test_includes_hostile_flag(self) -> None:
        """Each technique in the list includes a boolean hostile field."""
        benign = make_castable_technique(hostile=False)
        CharacterTechniqueFactory(character=self.identity, technique=benign)
        response = self.client.get(self._url(), {"initiator_persona": self.persona.pk})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        result = next(t for t in response.data if t["id"] == benign.pk)
        assert result["hostile"] is False

    def test_does_not_return_other_characters_techniques(self) -> None:
        """Techniques known only by another character do not appear."""
        technique = make_castable_technique()
        CharacterTechniqueFactory(character=self.other_identity, technique=technique)
        response = self.client.get(self._url(), {"initiator_persona": self.persona.pk})
        assert response.status_code == status.HTTP_200_OK
        ids = [t["id"] for t in response.data]
        assert technique.pk not in ids

    def test_missing_initiator_persona_returns_400(self) -> None:
        """Missing initiator_persona query param → 400."""
        response = self.client.get(self._url())
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_wrong_account_persona_returns_400(self) -> None:
        """Passing a persona that belongs to a different account → 400."""
        response = self.client.get(self._url(), {"initiator_persona": self.other_persona.pk})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_castable_techniques_returns_403(self) -> None:
        """Unauthenticated request to castable-techniques → 403."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self._url(), {"initiator_persona": self.persona.pk})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_response_contains_expected_fields(self) -> None:
        """Each entry has id, name, anima_cost, tier, intensity, control, hostile."""
        technique = make_castable_technique()
        CharacterTechniqueFactory(character=self.identity, technique=technique)
        response = self.client.get(self._url(), {"initiator_persona": self.persona.pk})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        entry = next(t for t in response.data if t["id"] == technique.pk)
        for field in ("id", "name", "anima_cost", "tier", "intensity", "control", "hostile"):
            assert field in entry, f"Field {field!r} missing from castable-technique entry"


class PerTargetRespondTestCase(APITestCase):
    """Tests for per-target consent via POST /api/action-requests/{id}/respond/ (#572 Task 5)."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Initiator account + persona
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterSheetFactory(character=cls.character)
        cls.persona = cls.identity.primary_persona

        # Primary target account + persona
        cls.target_account = AccountFactory()
        cls.target_character = CharacterFactory()
        cls.target_roster_entry = RosterEntryFactory(
            character_sheet__character=cls.target_character
        )
        cls.target_player_data = PlayerDataFactory(account=cls.target_account)
        cls.target_tenure = RosterTenureFactory(
            player_data=cls.target_player_data,
            roster_entry=cls.target_roster_entry,
        )
        cls.target_identity = CharacterSheetFactory(character=cls.target_character)
        cls.target_persona = cls.target_identity.primary_persona

        # Additional target account + persona
        cls.extra_account = AccountFactory()
        cls.extra_character = CharacterFactory()
        cls.extra_roster_entry = RosterEntryFactory(character_sheet__character=cls.extra_character)
        cls.extra_player_data = PlayerDataFactory(account=cls.extra_account)
        cls.extra_tenure = RosterTenureFactory(
            player_data=cls.extra_player_data,
            roster_entry=cls.extra_roster_entry,
        )
        cls.extra_identity = CharacterSheetFactory(character=cls.extra_character)
        cls.extra_persona = cls.extra_identity.primary_persona

        cls.scene = SceneFactory()

    def _make_request_with_additional(self) -> tuple:
        """Create a SceneActionRequest + a SceneActionTarget row for extra_persona."""
        action_request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.persona,
            target_persona=self.target_persona,
            action_key="persuade",
        )
        action_target = SceneActionTargetFactory(
            action_request=action_request,
            target_persona=self.extra_persona,
        )
        return action_request, action_target

    @patch("world.scenes.action_views.respond_to_action_target")
    def test_per_target_accept_resolves_that_row(self, mock_respond: MagicMock) -> None:
        """POSTing target_persona_id with accept calls respond_to_action_target on that row."""
        mock_respond.return_value = _make_enhanced_result("persuade")
        action_request, action_target = self._make_request_with_additional()
        self.client.force_authenticate(user=self.extra_account)
        url = reverse("sceneactionrequest-respond", kwargs={"pk": action_request.pk})
        response = self.client.post(
            url,
            {"decision": ConsentDecision.ACCEPT, "target_persona_id": self.extra_persona.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        mock_respond.assert_called_once_with(
            action_target=action_target,
            decision=ConsentDecision.ACCEPT,
            difficulty=None,
            resist_effort="",
        )
        # Response carries the row's id and action_request_id
        assert response.data["action_target_id"] == action_target.pk
        assert response.data["action_request_id"] == action_request.pk

    @patch("world.scenes.action_views.respond_to_action_target")
    def test_per_target_accept_primary_request_untouched(self, mock_respond: MagicMock) -> None:
        """Responding to an additional target row leaves the primary request PENDING."""
        mock_respond.return_value = None
        action_request, _action_target = self._make_request_with_additional()
        self.client.force_authenticate(user=self.extra_account)
        url = reverse("sceneactionrequest-respond", kwargs={"pk": action_request.pk})
        self.client.post(
            url,
            {"decision": ConsentDecision.DENY, "target_persona_id": self.extra_persona.pk},
            format="json",
        )
        action_request.refresh_from_db()
        assert action_request.status == ActionRequestStatus.PENDING

    def test_unknown_target_persona_id_returns_404(self) -> None:
        """A target_persona_id with no matching SceneActionTarget row → 404."""
        action_request, _ = self._make_request_with_additional()
        self.client.force_authenticate(user=self.extra_account)
        url = reverse("sceneactionrequest-respond", kwargs={"pk": action_request.pk})
        response = self.client.post(
            url,
            {"decision": ConsentDecision.ACCEPT, "target_persona_id": 999999},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_wrong_account_cannot_respond_for_another_persona_returns_403(self) -> None:
        """Requester who does not control that persona → 403."""
        action_request, _ = self._make_request_with_additional()
        # target_account controls target_persona, NOT extra_persona
        self.client.force_authenticate(user=self.target_account)
        url = reverse("sceneactionrequest-respond", kwargs={"pk": action_request.pk})
        response = self.client.post(
            url,
            {"decision": ConsentDecision.ACCEPT, "target_persona_id": self.extra_persona.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("world.scenes.action_views.respond_to_action_request")
    def test_absent_target_persona_id_uses_primary_path(self, mock_respond: MagicMock) -> None:
        """Omitting target_persona_id falls through to the original primary-target branch."""
        mock_respond.return_value = _make_enhanced_result("persuade")
        action_request, _ = self._make_request_with_additional()
        self.client.force_authenticate(user=self.target_account)
        url = reverse("sceneactionrequest-respond", kwargs={"pk": action_request.pk})
        response = self.client.post(
            url,
            {"decision": ConsentDecision.ACCEPT},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        mock_respond.assert_called_once()

    @patch("world.scenes.action_views.respond_to_action_target")
    def test_per_target_accept_value_error_returns_400(self, mock_respond: MagicMock) -> None:
        """A ValueError from respond_to_action_target (e.g. no action_template) returns 400."""
        mock_respond.side_effect = ValueError("Cannot resolve action: no ActionTemplate set.")
        action_request, _action_target = self._make_request_with_additional()
        self.client.force_authenticate(user=self.extra_account)
        url = reverse("sceneactionrequest-respond", kwargs={"pk": action_request.pk})
        response = self.client.post(
            url,
            {"decision": ConsentDecision.ACCEPT, "target_persona_id": self.extra_persona.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["detail"] == "Unable to process this action request."


class TestSceneActionTargetViewSet(APITestCase):
    """GET /api/action-targets/ lists the requester's pending additional-target rows (#1177)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.player_data = PlayerDataFactory(account=cls.account)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player_data,
            roster_entry=cls.roster_entry,
        )
        cls.identity = CharacterSheetFactory(character=cls.character)
        cls.my_persona = cls.identity.primary_persona

        cls.other_account = AccountFactory()
        cls.other_character = CharacterFactory()
        cls.other_roster_entry = RosterEntryFactory(character_sheet__character=cls.other_character)
        cls.other_player_data = PlayerDataFactory(account=cls.other_account)
        cls.other_tenure = RosterTenureFactory(
            player_data=cls.other_player_data,
            roster_entry=cls.other_roster_entry,
        )
        cls.other_identity = CharacterSheetFactory(character=cls.other_character)
        cls.other_persona = cls.other_identity.primary_persona

        cls.scene = SceneFactory()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)

    def test_lists_only_my_pending_target_rows(self) -> None:
        request = SceneActionRequestFactory(scene=self.scene, initiator_persona=self.other_persona)
        mine = SceneActionTargetFactory(
            action_request=request,
            target_persona=self.my_persona,
            status=ActionRequestStatus.PENDING,
        )
        SceneActionTargetFactory(  # someone else's row — must not appear
            action_request=request,
            target_persona=self.other_persona,
            status=ActionRequestStatus.PENDING,
        )

        resp = self.client.get(f"/api/action-targets/?scene={self.scene.pk}&status=pending")

        self.assertEqual(resp.status_code, 200)
        ids = [r["action_target_id"] for r in resp.json()["results"]]
        self.assertEqual(ids, [mine.pk])
        row = resp.json()["results"][0]
        self.assertEqual(row["target_persona_id"], self.my_persona.pk)
        self.assertEqual(row["initiator_name"], self.other_persona.name)
        self.assertIn("action_key", row)
        self.assertIn("pose_text", row)

    def test_status_filter_excludes_resolved(self) -> None:
        request = SceneActionRequestFactory(scene=self.scene, initiator_persona=self.other_persona)
        SceneActionTargetFactory(
            action_request=request,
            target_persona=self.my_persona,
            status=ActionRequestStatus.RESOLVED,
        )
        resp = self.client.get(f"/api/action-targets/?scene={self.scene.pk}&status=pending")
        self.assertEqual(resp.json()["results"], [])
