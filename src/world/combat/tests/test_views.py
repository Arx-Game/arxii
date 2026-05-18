"""Tests for CombatEncounterViewSet."""

from django.test import TestCase
from rest_framework import status as http_status
from rest_framework.test import APIClient

from actions.errors import ActionDispatchError
from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import EncounterStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction
from world.magic.factories import (
    BinaryEffectTypeFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
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

    def test_resolve_round_returns_400_for_technique_missing_action_template(self) -> None:
        """resolve_round returns HTTP 400 with safe user_message when a declared
        technique has no action_template (ActionDispatchError, not ValueError).

        The @transaction.atomic on resolve_round rolls back the RESOLVING status
        write, so the encounter remains DECLARING after the 400 response.
        """
        # Encounter must be in DECLARING state with round_number set
        declaring_encounter = CombatEncounterFactory(
            scene=self.scene,
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        participant = CombatParticipantFactory(
            encounter=declaring_encounter,
            character_sheet=self.player_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        # CharacterVitals required so the participant appears in resolution order
        CharacterVitals.objects.get_or_create(
            character_sheet=self.player_sheet,
            defaults={"health": 100, "max_health": 100},
        )
        # Technique with no action_template — triggers TECHNIQUE_NOT_COMBAT_READY
        technique = TechniqueFactory(action_template=None)
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_action=technique,
        )

        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.post(
            f"/api/combat/{declaring_encounter.pk}/resolve_round/",
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        expected_message = ActionDispatchError(
            ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY
        ).user_message
        self.assertEqual(response.data["detail"], expected_message)


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

    def test_join_requires_character_sheet_id(self) -> None:
        """POST /join without character_sheet_id returns 400."""
        # Use a fresh account with no existing participation
        joiner_account = AccountFactory(username="joiner_no_id")
        joiner_character = CharacterFactory(db_key="joiner_no_id_char")
        CharacterSheetFactory(character=joiner_character)
        RosterTenureFactory(
            roster_entry__character_sheet__character=joiner_character,
            player_data__account=joiner_account,
        )
        # Encounter must accept a same-room join — easiest: use the scene one,
        # which IsInEncounterRoom is bypassed for staff... use staff to skip
        # the room check and isolate the validation behavior.
        staff = AccountFactory(username="join_check_staff", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff)
        response = client.post(f"/api/combat/{self.encounter.pk}/join/")
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_join_rejects_other_users_character(self) -> None:
        """POST /join with a character the user does not play returns 403."""
        client = APIClient()
        client.force_authenticate(user=self.player_account)
        # Pass the GM's sheet pk — the player doesn't play it.
        response = client.post(
            f"/api/combat/{self.encounter.pk}/join/",
            {"character_sheet_id": self.gm_sheet.pk},
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

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

    def test_declare_ally_target_persisted_via_endpoint(self) -> None:
        """Declaring a self/ally-cast technique via the DRF endpoint persists focused_ally_target.

        This is the TDD red test: DeclareActionSerializer has no focused_ally_target
        field, so the view hardcodes focused_ally_target=None, dropping the ally choice.
        The test must fail because CombatRoundAction.focused_ally_target is None instead
        of the ally participant.
        """
        # Buff effect type (no base_power → no damage → no forced opponent target)
        buff_effect_type = BinaryEffectTypeFactory()
        # Technique with action_template so serializer validation passes,
        # and one ally-kind condition row so target-kind validation passes
        technique = TechniqueFactory(
            effect_type=buff_effect_type,
            damage_profile=False,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        TechniqueAppliedConditionFactory(technique=technique, target_kind="ally")

        # Fresh DECLARING encounter linked to the scene so setUpTestData doesn't interfere
        declare_encounter = CombatEncounterFactory(
            scene=self.scene,
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        # Caster — use player_sheet so player_account's played_character_sheet_ids matches
        caster_participant = CombatParticipantFactory(
            encounter=declare_encounter,
            character_sheet=self.player_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterVitals.objects.get_or_create(
            character_sheet=self.player_sheet,
            defaults={"health": 100, "max_health": 100},
        )
        # Ally — a second participant in the same encounter
        ally_participant = CombatParticipantFactory(
            encounter=declare_encounter,
            status=ParticipantStatus.ACTIVE,
        )

        client = APIClient()
        client.force_authenticate(user=self.player_account)
        response = client.post(
            f"/api/combat/{declare_encounter.pk}/declare/",
            {
                "focused_action": technique.pk,
                "focused_category": "physical",
                "effort_level": "medium",
                "focused_ally_target": ally_participant.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        # Reload the persisted action and assert the ally target was stored
        action = CombatRoundAction.objects.get(
            participant=caster_participant,
            round_number=declare_encounter.round_number,
        )
        self.assertEqual(action.focused_ally_target, ally_participant)


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
