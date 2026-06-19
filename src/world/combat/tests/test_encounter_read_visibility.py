"""Tests for encounter read visibility gated by scene visibility (#1041).

Covers:
- Outsider cannot list or retrieve a private-scene encounter (404, not 403).
- Scene member (SceneParticipation) can read.
- Combat participant WITHOUT a SceneParticipation row can read (regression guard —
  combat never creates SceneParticipation rows).
- Staff bypass: staff see all.
- Public scene encounter is visible to any authenticated user.
- Action routes (e.g. my_action) are NOT filtered — a participant in a private
  scene who has no SceneParticipation still resolves the encounter on action routes.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.constants import ScenePrivacyMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory


class EncounterReadVisibilityTests(TestCase):
    """Gate encounter list/retrieve by scene visibility."""

    @classmethod
    def setUpTestData(cls) -> None:
        # --- Private scene with a combat encounter ---
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)

        # member: has a SceneParticipation but is NOT a combat participant
        cls.member_account = AccountFactory(username="vis_member")
        SceneParticipationFactory(scene=cls.scene, account=cls.member_account)

        # fighter: IS a combat participant but has NO SceneParticipation row
        cls.fighter_account = AccountFactory(username="vis_fighter")
        cls.fighter_character = CharacterFactory(db_key="VisFighterChar")
        cls.fighter_sheet = CharacterSheetFactory(character=cls.fighter_character)
        # Wire a RosterTenure so played_character_sheet_ids includes fighter_sheet.pk
        cls.fighter_tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.fighter_character,
            player_data__account=cls.fighter_account,
        )

        # outsider: neither SceneParticipation nor combat participant
        cls.outsider_account = AccountFactory(username="vis_outsider")

        # staff: is_staff=True — bypasses all filters
        cls.staff_account = AccountFactory(username="vis_staff", is_staff=True)

        # Encounter on the private scene
        cls.encounter = CombatEncounterFactory(scene=cls.scene)

        # Wire the fighter as a CombatParticipant (no SceneParticipation)
        cls.fighter_participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.fighter_sheet,
            status=ParticipantStatus.ACTIVE,
        )

        # --- Public scene with a separate encounter (for the public-scene test) ---
        cls.public_scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.public_encounter = CombatEncounterFactory(scene=cls.public_scene)

    # ------------------------------------------------------------------
    # list tests
    # ------------------------------------------------------------------

    def test_outsider_cannot_list_private_encounter(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.outsider_account)
        response = client.get("/api/combat/")
        self.assertEqual(response.status_code, 200)
        ids = {e["id"] for e in response.data["results"]}
        self.assertNotIn(self.encounter.id, ids)

    def test_scene_member_can_list_private_encounter(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.member_account)
        response = client.get("/api/combat/")
        self.assertEqual(response.status_code, 200)
        ids = {e["id"] for e in response.data["results"]}
        self.assertIn(self.encounter.id, ids)

    def test_fighter_without_scene_participation_can_list(self) -> None:
        """Regression guard: combat participant visible in list even with no SceneParticipation."""
        client = APIClient()
        client.force_authenticate(user=self.fighter_account)
        response = client.get("/api/combat/")
        self.assertEqual(response.status_code, 200)
        ids = {e["id"] for e in response.data["results"]}
        self.assertIn(self.encounter.id, ids)

    # ------------------------------------------------------------------
    # retrieve tests
    # ------------------------------------------------------------------

    def test_outsider_retrieve_is_404(self) -> None:
        """Non-viewable encounters must produce 404, not 403 — no existence leak."""
        client = APIClient()
        client.force_authenticate(user=self.outsider_account)
        response = client.get(f"/api/combat/{self.encounter.id}/")
        self.assertEqual(response.status_code, 404)

    def test_scene_member_can_retrieve(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.member_account)
        response = client.get(f"/api/combat/{self.encounter.id}/")
        self.assertEqual(response.status_code, 200)

    def test_fighter_without_scene_participation_can_retrieve(self) -> None:
        """Regression guard: combat never creates SceneParticipation rows."""
        client = APIClient()
        client.force_authenticate(user=self.fighter_account)
        response = client.get(f"/api/combat/{self.encounter.id}/")
        self.assertEqual(response.status_code, 200)

    def test_staff_can_retrieve_private_encounter(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff_account)
        response = client.get(f"/api/combat/{self.encounter.id}/")
        self.assertEqual(response.status_code, 200)

    def test_public_scene_visible_to_any_authenticated(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.outsider_account)
        response = client.get(f"/api/combat/{self.public_encounter.id}/")
        self.assertEqual(response.status_code, 200)

    # ------------------------------------------------------------------
    # action-route no-lockout regression
    # ------------------------------------------------------------------

    def test_action_route_resolves_for_fighter_in_private_scene(self) -> None:
        """Action routes must NOT be filtered by scene visibility.

        A combat participant in a private scene with no SceneParticipation row
        must still be able to hit action routes (my_action, etc.). If the read
        filter were also applied to action routes, fighters would be locked out
        of their own encounter.
        """
        client = APIClient()
        client.force_authenticate(user=self.fighter_account)
        # my_action returns 200 with None body when no round action declared yet
        response = client.get(f"/api/combat/{self.encounter.id}/my_action/")
        self.assertEqual(response.status_code, 200)
