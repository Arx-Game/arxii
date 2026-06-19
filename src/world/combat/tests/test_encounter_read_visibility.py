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
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.views import CombatEncounterViewSet
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


class GetQuerysetGuardIsolationTests(TestCase):
    """Unit-level proof that the ('list','retrieve') guard in get_queryset() is load-bearing.

    The existing HTTP-level tests check end-to-end visibility, but an outsider who
    is also an encounter participant would pass _filter_readable even if the guard
    were removed — so they don't isolate the guard itself. This class does:

    - For action='retrieve', an outsider (no SceneParticipation, no played characters)
      must NOT see the private-scene encounter.
    - For action='begin_round' (a non-read action), the SAME outsider MUST see it
      — the unfiltered base queryset is returned.

    Deleting the ``if self.action in ("list", "retrieve")`` guard from get_queryset()
    would collapse these two assertions to the same result → test fails.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.private_scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        cls.encounter = CombatEncounterFactory(scene=cls.private_scene)
        # outsider: not staff, no SceneParticipation, no played characters
        cls.outsider_account = AccountFactory(username="guard_outsider")
        cls._factory = APIRequestFactory()

    def _make_view(self, action: str) -> CombatEncounterViewSet:
        """Return a viewset instance wired with an outsider request and the given action.

        ``action_map`` is normally set by the router via ``.as_view()``;
        we set it explicitly so ``initialize_request`` (which reads it to
        resolve the current action from the HTTP method) doesn't raise.
        We then override ``view.action`` directly because we don't want the
        router's method→action lookup — we're controlling the action name
        to probe the guard branch directly.
        """
        raw_request = self._factory.get("/")
        force_authenticate(raw_request, user=self.outsider_account)
        view = CombatEncounterViewSet()
        view.action_map = {"get": action}
        # initialize_request wraps the WSGIRequest in a DRF Request so that
        # view.request.user is populated correctly (mirrors what the router does).
        view.request = view.initialize_request(raw_request)
        # Override the action explicitly after initialize_request sets it from
        # action_map; this ensures the guard branch we test is the one we named.
        view.action = action
        view.kwargs = {}
        view.format_kwarg = None
        return view

    def test_retrieve_excludes_private_encounter_for_outsider(self) -> None:
        """_filter_readable is applied for action='retrieve': outsider sees nothing."""
        view = self._make_view("retrieve")
        pks = set(view.get_queryset().values_list("pk", flat=True))
        self.assertNotIn(
            self.encounter.pk,
            pks,
            "Private encounter must be excluded for an outsider on retrieve.",
        )

    def test_non_read_action_includes_private_encounter_for_outsider(self) -> None:
        """Unfiltered base queryset is returned for action='begin_round': encounter visible."""
        view = self._make_view("begin_round")
        pks = set(view.get_queryset().values_list("pk", flat=True))
        self.assertIn(
            self.encounter.pk,
            pks,
            "Private encounter must be included on non-read actions (unfiltered path).",
        )
