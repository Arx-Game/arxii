"""Tests for the opponent-defaults preview endpoint and stakes-gated add_opponent (Task 6, #566).

Covers:
- GET opponent-defaults?tier=elite as encounter GM → 200, block fields + stakes_ok=True
- GET with a party/GM under the stakes gate → 200, stakes_ok=False, non-empty stakes_message
- GET with missing/invalid tier → 400
- GET as non-GM/non-staff → 403
- add_opponent POST over the stakes gate → 400 with the gate message
- add_opponent POST with qualifying GM + party → 201/200 success
"""

from django.test import TestCase
from rest_framework import status as http_status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.classes.factories import CharacterClassLevelFactory
from world.combat.constants import OpponentTier, ParticipantStatus, RiskLevel, StakesLevel
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    StakesLevelRequirementFactory,
    ThreatPoolFactory,
    seed_scaling_defaults,
)
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


class OpponentDefaultsTestBase(TestCase):
    """Shared setup: scene, GM account, encounter, party participant."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_scaling_defaults()

        # GM account with a tenure so played_character_sheet_ids works
        cls.gm_account = AccountFactory(username="scalinggm")

        # Non-GM player account
        cls.player_account = AccountFactory(username="scalingplayer")
        cls.player_tenure = RosterTenureFactory(
            player_data__account=cls.player_account,
        )
        cls.player_sheet = cls.player_tenure.roster_entry.character_sheet

        # Scene with GM participation
        cls.scene = SceneFactory()
        SceneParticipationFactory(
            scene=cls.scene,
            account=cls.gm_account,
            is_gm=True,
        )

        # Encounter at REGIONAL stakes so gates can be tested
        cls.encounter = CombatEncounterFactory(
            scene=cls.scene,
            stakes_level=StakesLevel.REGIONAL,
            risk_level=RiskLevel.MODERATE,
        )

        # Add one ACTIVE participant so avg_level is non-zero
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.player_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        # Give the participant a primary class level of 10 (above any sane gate)
        CharacterClassLevelFactory(
            character=cls.player_sheet,
            level=10,
            is_primary=True,
        )


class OpponentDefaultsGMQualifyingTest(OpponentDefaultsTestBase):
    """GET opponent-defaults?tier=elite as qualifying GM → 200, block + stakes_ok=True."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # REGIONAL gate: avg_level >= 5, gm_level >= JUNIOR.
        # Default seed sets minimum_party_average_level=5, minimum_gm_level=JUNIOR.
        # We override to ensure a controlled threshold.
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=5,
            minimum_gm_level=GMLevel.JUNIOR,
        )
        # GM level is GM (above JUNIOR)
        GMProfileFactory(account=cls.gm_account, level=GMLevel.GM)

    def test_gm_qualifying_returns_200(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

    def test_response_has_block_fields(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        data = response.data
        self.assertIn("max_health", data)
        self.assertIn("soak_value", data)
        self.assertIn("probing_threshold", data)
        self.assertIn("swarm_count", data)
        self.assertIn("body_toughness", data)
        self.assertIn("bodies_per_attack", data)
        self.assertIn("barrier_strength", data)
        self.assertIn("phases", data)

    def test_stakes_ok_true_when_qualifying(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertTrue(response.data["stakes_ok"])

    def test_stakes_message_empty_when_qualifying(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertEqual(response.data["stakes_message"], "")

    def test_max_health_is_positive_integer(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertGreater(response.data["max_health"], 0)

    def test_phases_is_list(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertIsInstance(response.data["phases"], list)

    def test_boss_tier_phases_non_empty(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=boss",
        )
        self.assertGreater(len(response.data["phases"]), 0)

    def test_boss_phase_has_expected_fields(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=boss",
        )
        phase = response.data["phases"][0]
        self.assertIn("phase_number", phase)
        self.assertIn("health_trigger_percentage", phase)
        self.assertIn("soak_value", phase)
        self.assertIn("probing_threshold", phase)


class OpponentDefaultsStakesFailTest(OpponentDefaultsTestBase):
    """GET opponent-defaults with party/GM under stakes gate → 200 + stakes_ok=False."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Set a very high threshold so the GM fails
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=50,  # party avg is 10 → fails
            minimum_gm_level=GMLevel.STARTING,
        )
        # GM has no GMProfile (defaults to STARTING which passes the level gate,
        # but party level gate fires first)

    def test_under_gate_still_returns_200(self) -> None:
        """Preview should return 200 even when stakes gate is not met."""
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

    def test_stakes_ok_false_when_under_gate(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertFalse(response.data["stakes_ok"])

    def test_stakes_message_non_empty_when_under_gate(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertTrue(response.data["stakes_message"])

    def test_block_fields_still_present_when_under_gate(self) -> None:
        """Block data is returned even when stakes_ok=False (preview must show both)."""
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertIn("max_health", response.data)
        self.assertGreater(response.data["max_health"], 0)


class OpponentDefaultsInvalidTierTest(OpponentDefaultsTestBase):
    """GET with missing/invalid tier → 400."""

    def test_missing_tier_returns_400(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/",
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_invalid_tier_returns_400(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=godmode",
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)


class OpponentDefaultsPermissionTest(OpponentDefaultsTestBase):
    """Non-GM / non-staff cannot call the preview endpoint."""

    def test_non_gm_returns_403(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.player_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_returns_403(self) -> None:
        client = APIClient()
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_staff_can_access_preview(self) -> None:
        """Staff bypass applies to the preview endpoint."""
        staff_account = AccountFactory(username="staffuser", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff_account)
        response = client.get(
            f"/api/combat/{self.encounter.pk}/opponent-defaults/?tier=elite",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)


# =============================================================================
# add_opponent stakes validation
# =============================================================================


class AddOpponentStakesValidationTestBase(TestCase):
    """Base: scene, encounter at REGIONAL stakes, qualifying/failing GM variants."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_scaling_defaults()

        cls.gm_account = AccountFactory(username="addoppgm")
        cls.scene = SceneFactory()
        SceneParticipationFactory(
            scene=cls.scene,
            account=cls.gm_account,
            is_gm=True,
        )

        cls.encounter = CombatEncounterFactory(
            scene=cls.scene,
            stakes_level=StakesLevel.REGIONAL,
            risk_level=RiskLevel.MODERATE,
        )

        # One ACTIVE participant at level 10
        cls.player_tenure = RosterTenureFactory()
        cls.player_sheet = cls.player_tenure.roster_entry.character_sheet
        CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.player_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterClassLevelFactory(
            character=cls.player_sheet,
            level=10,
            is_primary=True,
        )

        cls.pool = ThreatPoolFactory()


class AddOpponentStakesGateBlocksTest(AddOpponentStakesValidationTestBase):
    """add_opponent over the stakes gate → 400 with the gate message."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Set a very high threshold: party avg 10, but minimum is 50
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=50,
            minimum_gm_level=GMLevel.STARTING,
        )

    def test_add_opponent_over_gate_returns_400(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.post(
            f"/api/combat/{self.encounter.pk}/add_opponent/",
            {
                "name": "Gate Blocked Goblin",
                "tier": OpponentTier.ELITE,
                "threat_pool_id": self.pool.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_add_opponent_400_has_gate_message(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.post(
            f"/api/combat/{self.encounter.pk}/add_opponent/",
            {
                "name": "Gate Blocked Goblin",
                "tier": OpponentTier.ELITE,
                "threat_pool_id": self.pool.pk,
            },
            format="json",
        )
        self.assertIn("non_field_errors", response.data)
        self.assertTrue(response.data["non_field_errors"])


class AddOpponentStakesQualifyingTest(AddOpponentStakesValidationTestBase):
    """add_opponent with qualifying GM + party → success (200/201)."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # seed_scaling_defaults() sets REGIONAL minimum_gm_level=JUNIOR.
        # Give the GM sufficient level so both gates pass.
        GMProfileFactory(account=cls.gm_account, level=GMLevel.GM)

    def test_add_opponent_qualifying_succeeds(self) -> None:
        """setUp creates a fresh encounter to avoid DB contamination from opponent creation."""
        encounter = CombatEncounterFactory(
            scene=self.scene,
            stakes_level=StakesLevel.REGIONAL,
            risk_level=RiskLevel.MODERATE,
        )
        # Add participant with level 10 to this new encounter
        player_tenure = RosterTenureFactory()
        player_sheet = player_tenure.roster_entry.character_sheet
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=player_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterClassLevelFactory(
            character=player_sheet,
            level=10,
            is_primary=True,
        )

        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.post(
            f"/api/combat/{encounter.pk}/add_opponent/",
            {
                "name": "Qualifying Goblin",
                "tier": OpponentTier.MOOK,
                "threat_pool_id": self.pool.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

    def test_add_opponent_with_explicit_max_health_qualifying_succeeds(self) -> None:
        """Explicit max_health (manual mode) with qualifying stakes passes."""
        encounter = CombatEncounterFactory(
            scene=self.scene,
            stakes_level=StakesLevel.REGIONAL,
            risk_level=RiskLevel.MODERATE,
        )
        player_tenure = RosterTenureFactory()
        player_sheet = player_tenure.roster_entry.character_sheet
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=player_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterClassLevelFactory(
            character=player_sheet,
            level=10,
            is_primary=True,
        )

        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.post(
            f"/api/combat/{encounter.pk}/add_opponent/",
            {
                "name": "Manual Goblin",
                "tier": OpponentTier.MOOK,
                "max_health": 30,
                "threat_pool_id": self.pool.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
