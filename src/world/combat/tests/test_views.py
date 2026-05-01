"""Tests for CombatEncounterViewSet."""

from django.test import TestCase
from rest_framework import status as http_status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolFactory,
)
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.vitals.models import CharacterVitals


class CombatEncounterViewSetTestBase(TestCase):
    """Shared setup for view tests."""

    @classmethod
    def setUpTestData(cls) -> None:
        # GM account and character
        cls.gm_account = AccountFactory(username="testgm")
        cls.gm_character = CharacterFactory(db_key="gmchar")
        cls.gm_sheet = CharacterSheetFactory(character=cls.gm_character)
        cls.gm_tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.gm_character,
            player_data__account=cls.gm_account,
        )

        # Player account and character
        cls.player_account = AccountFactory(username="testplayer")
        cls.player_character = CharacterFactory(db_key="playerchar")
        cls.player_sheet = CharacterSheetFactory(
            character=cls.player_character,
        )
        cls.player_tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.player_character,
            player_data__account=cls.player_account,
        )

        # Scene with GM participation
        cls.scene = SceneFactory()
        SceneParticipationFactory(
            scene=cls.scene,
            account=cls.gm_account,
            is_gm=True,
        )

        # Encounter linked to scene
        cls.encounter = CombatEncounterFactory(scene=cls.scene)

        # Player is a participant
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.player_sheet,
            status=ParticipantStatus.ACTIVE,
        )


class ListRetrieveTest(CombatEncounterViewSetTestBase):
    """Tests for list and retrieve permissions."""

    def test_list_requires_auth(self) -> None:
        client = APIClient()
        response = client.get("/api/combat/")
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_list_authenticated(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get("/api/combat/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

    def test_retrieve_authenticated(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.player_account)
        response = client.get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.encounter.pk)

    def test_retrieve_unauthenticated(self) -> None:
        client = APIClient()
        response = client.get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)


class GMLifecycleTest(CombatEncounterViewSetTestBase):
    """Tests for GM-only lifecycle actions.

    Creates a fresh encounter in setUp (not setUpTestData) so that CombatNPCs
    created during test methods don't contaminate the room's Evennia identity-map
    cache across tests (DbHolder is not deepcopyable, which breaks setUpTestData).
    """

    def setUp(self) -> None:
        # Fresh encounter per test to avoid CombatNPC identity-map contamination.
        self.encounter = CombatEncounterFactory(scene=self.scene)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.player_sheet,
            status=ParticipantStatus.ACTIVE,
        )

    def test_begin_round_as_gm(self) -> None:
        """GM can begin a round when encounter is BETWEEN_ROUNDS."""
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        # Ensure encounter has at least one opponent (required by service)
        CombatOpponentFactory(encounter=self.encounter)
        response = client.post(
            f"/api/combat/{self.encounter.pk}/begin_round/",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, EncounterStatus.DECLARING)
        self.assertEqual(self.encounter.round_number, 1)

    def test_begin_round_non_gm_denied(self) -> None:
        """Non-GM player cannot begin a round."""
        client = APIClient()
        client.force_authenticate(user=self.player_account)
        response = client.post(
            f"/api/combat/{self.encounter.pk}/begin_round/",
        )
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_begin_round_unauthenticated(self) -> None:
        client = APIClient()
        response = client.post(
            f"/api/combat/{self.encounter.pk}/begin_round/",
        )
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_add_opponent_as_gm(self) -> None:
        """GM can add an opponent."""
        pool = ThreatPoolFactory()
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.post(
            f"/api/combat/{self.encounter.pk}/add_opponent/",
            {
                "name": "Goblin",
                "tier": "mook",
                "max_health": 30,
                "threat_pool_id": pool.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(
            self.encounter.opponents.count(),
            1,
        )

    def test_pause_as_gm(self) -> None:
        """GM can toggle pause."""
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.post(
            f"/api/combat/{self.encounter.pk}/pause/",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.encounter.refresh_from_db()
        self.assertTrue(self.encounter.is_paused)

    def test_remove_participant_as_gm(self) -> None:
        """GM can remove a participant."""
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.post(
            f"/api/combat/{self.encounter.pk}/remove_participant/",
            {"participant_id": self.participant.pk},
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.participant.refresh_from_db()
        self.assertEqual(
            self.participant.status,
            ParticipantStatus.REMOVED,
        )


class PlayerActionTest(CombatEncounterViewSetTestBase):
    """Tests for player action endpoints."""

    def test_my_action_no_action_declared(self) -> None:
        """Returns null when no action has been declared."""
        client = APIClient()
        client.force_authenticate(user=self.player_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/my_action/",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertIsNone(response.data)

    def test_declare_non_participant_denied(self) -> None:
        """Account with no participant in encounter gets 403."""
        other_account = AccountFactory(username="outsider")
        other_char = CharacterFactory(db_key="outsiderchar")
        CharacterSheetFactory(character=other_char)
        RosterTenureFactory(
            roster_entry__character_sheet__character=other_char,
            player_data__account=other_account,
        )
        client = APIClient()
        client.force_authenticate(user=other_account)
        response = client.post(
            f"/api/combat/{self.encounter.pk}/declare/",
            {"effort_level": "medium"},
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_ready_toggle(self) -> None:
        """Participant can toggle ready on their action if one exists."""
        # First we need an action — create one directly
        from world.combat.models import CombatRoundAction

        CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=self.encounter.round_number,
            effort_level="medium",
        )
        client = APIClient()
        client.force_authenticate(user=self.player_account)
        response = client.post(
            f"/api/combat/{self.encounter.pk}/ready/",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

    def test_flee_marks_participant_fled(self) -> None:
        """Flee endpoint marks the participant as FLED."""
        # Use a separate encounter in DECLARING status for the flee test
        flee_encounter = CombatEncounterFactory(
            scene=self.scene,
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        flee_participant = CombatParticipantFactory(
            encounter=flee_encounter,
            character_sheet=self.player_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterVitals.objects.get_or_create(
            character_sheet=self.player_sheet,
            defaults={"health": 50, "max_health": 100},
        )
        client = APIClient()
        client.force_authenticate(user=self.player_account)
        response = client.post(
            f"/api/combat/{flee_encounter.pk}/flee/",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        flee_participant.refresh_from_db()
        self.assertEqual(
            flee_participant.status,
            ParticipantStatus.FLED,
        )


class StaffAccessTest(TestCase):
    """Staff can access GM endpoints without being scene GM.

    Uses setUp (not setUpTestData) because CombatOpponentFactory creates a CombatNPC
    ObjectDB at the encounter's room, which would break setUpTestData deepcopy.
    """

    def setUp(self) -> None:
        self.staff = AccountFactory(username="staffuser", is_staff=True)
        self.encounter = CombatEncounterFactory(scene=SceneFactory())
        CombatOpponentFactory(encounter=self.encounter)

    def test_staff_begin_round(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.post(
            f"/api/combat/{self.encounter.pk}/begin_round/",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
