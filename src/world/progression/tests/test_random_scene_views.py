"""
Tests for Random Scene API views.
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterIdentityFactory
from world.game_clock.models import GameWeek
from world.game_clock.week_services import advance_game_week, get_current_game_week
from world.progression.models import RandomSceneCompletion, RandomSceneTarget
from world.roster.factories import PlayerDataFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


def _flush_caches() -> None:
    """Flush SharedMemoryModel caches for random scene models."""
    RandomSceneTarget.flush_instance_cache()
    RandomSceneCompletion.flush_instance_cache()
    GameWeek.flush_instance_cache()


def _make_active_character(account: AccountDB | None = None) -> tuple:
    """Helper: create a character with an active roster tenure and PRIMARY persona.

    Returns (persona, entry, tenure).
    """
    kwargs = {}
    if account is not None:
        kwargs["player_data"] = PlayerDataFactory(account=account)
    tenure = RosterTenureFactory(**kwargs)
    entry = tenure.roster_entry
    identity = CharacterIdentityFactory(character=entry.character)
    persona = identity.active_persona
    return persona, entry, tenure


class RandomSceneViewTestCase(TestCase):
    """Base test case with authenticated API client and random scene targets."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountDB.objects.create_user(
            username="rs_view_user",
            email="rs_view@test.com",
            password="testpass123",
        )
        cls.game_week = get_current_game_week()

        # Create own character with active tenure
        cls.own_persona, cls.own_entry, _ = _make_active_character(cls.account)

        # Create a target character with active tenure
        cls.target_account = AccountFactory(username="rs_target_user")
        cls.target_persona, cls.target_entry, _ = _make_active_character(cls.target_account)

        # Create a random scene target
        cls.target = RandomSceneTarget.objects.create(
            account=cls.account,
            target_persona=cls.target_persona,
            game_week=cls.game_week,
            slot_number=1,
            first_time=True,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        _flush_caches()


class ListRandomSceneTargetsTests(RandomSceneViewTestCase):
    """Tests for GET /api/progression/random-scenes/."""

    def test_list_returns_current_week_targets(self) -> None:
        """Returns current week's targets for the authenticated user."""
        response = self.client.get("/api/progression/random-scenes/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == self.target.pk
        assert response.data[0]["target_persona_name"] == self.target_persona.name
        assert response.data[0]["slot_number"] == 1
        assert response.data[0]["claimed"] is False
        assert response.data[0]["first_time"] is True
        assert response.data[0]["rerolled"] is False

    def test_list_excludes_other_users(self) -> None:
        """Does not include targets from other users."""
        other_user = AccountDB.objects.create_user(
            username="rs_other_list",
            email="rs_other_list@test.com",
            password="testpass123",
        )
        other_persona, _other_entry, _ = _make_active_character()
        RandomSceneTarget.objects.create(
            account=other_user,
            target_persona=other_persona,
            game_week=self.game_week,
            slot_number=1,
            first_time=False,
        )
        _flush_caches()
        self.client.force_authenticate(user=other_user)
        response = self.client.get("/api/progression/random-scenes/")
        assert response.status_code == status.HTTP_200_OK
        # Should only see the other user's target, not cls.account's
        target_ids = {t["id"] for t in response.data}
        assert self.target.pk not in target_ids

    def test_list_excludes_old_week(self) -> None:
        """Does not include targets from a previous week."""
        # Advance to create a new week, then create a target on the old week
        old_week = self.game_week
        new_week = advance_game_week()
        _flush_caches()

        old_persona, _old_entry, _ = _make_active_character()
        RandomSceneTarget.objects.create(
            account=self.account,
            target_persona=old_persona,
            game_week=old_week,
            slot_number=2,
            first_time=False,
        )
        _flush_caches()
        response = self.client.get("/api/progression/random-scenes/")
        assert response.status_code == status.HTTP_200_OK
        # The current week is now new_week, so only targets on new_week are returned
        # The original target from setUpTestData was on old_week
        for t in response.data:
            assert t.get("id") != self.target.pk or self.game_week == new_week

    def test_list_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are denied."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/progression/random-scenes/")
        assert response.status_code == status.HTTP_403_FORBIDDEN


class ClaimRandomSceneTests(RandomSceneViewTestCase):
    """Tests for POST /api/progression/random-scenes/<id>/claim/."""

    def _create_shared_scene(self) -> None:
        """Create a shared scene between account and target_account for validation."""
        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=self.account)
        SceneParticipationFactory(scene=scene, account=self.target_account)

    def test_claim_returns_200_with_xp_info(self) -> None:
        """Claiming a valid target returns 200 with updated target data."""
        self._create_shared_scene()
        _flush_caches()
        response = self.client.post(f"/api/progression/random-scenes/{self.target.pk}/claim/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["claimed"] is True
        assert response.data["claimed_at"] is not None
        assert response.data["first_time"] is True

    def test_claim_without_rp_evidence_returns_400(self) -> None:
        """Claiming without shared scene evidence returns 400."""
        response = self.client.post(f"/api/progression/random-scenes/{self.target.pk}/claim/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            "evidence" in response.data["detail"].lower()
            or "scene" in response.data["detail"].lower()
        )

    def test_claim_already_claimed_returns_400(self) -> None:
        """Claiming an already-claimed target returns 400."""
        self._create_shared_scene()
        _flush_caches()
        # Claim once
        self.client.post(f"/api/progression/random-scenes/{self.target.pk}/claim/")
        _flush_caches()
        # Try to claim again
        response = self.client.post(f"/api/progression/random-scenes/{self.target.pk}/claim/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already" in response.data["detail"].lower()

    def test_claim_nonexistent_returns_400(self) -> None:
        """Claiming a non-existent target returns 400."""
        response = self.client.post("/api/progression/random-scenes/999999/claim/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_claim_other_users_target_returns_400(self) -> None:
        """Cannot claim another user's target."""
        other_user = AccountDB.objects.create_user(
            username="rs_other_claim",
            email="rs_other_claim@test.com",
            password="testpass123",
        )
        other_persona, _other_entry, _ = _make_active_character()
        other_target = RandomSceneTarget.objects.create(
            account=other_user,
            target_persona=other_persona,
            game_week=self.game_week,
            slot_number=1,
            first_time=False,
        )
        _flush_caches()
        response = self.client.post(f"/api/progression/random-scenes/{other_target.pk}/claim/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_claim_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are denied."""
        self.client.force_authenticate(user=None)
        response = self.client.post(f"/api/progression/random-scenes/{self.target.pk}/claim/")
        assert response.status_code == status.HTTP_403_FORBIDDEN


class RerollRandomSceneTests(RandomSceneViewTestCase):
    """Tests for POST /api/progression/random-scenes/<id>/reroll/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Create additional active characters so reroll has candidates
        for _ in range(5):
            _make_active_character()

    def test_reroll_returns_200_with_new_character(self) -> None:
        """Rerolling a target returns 200 with a new target persona."""
        original_persona_id = self.target.target_persona_id
        response = self.client.post(f"/api/progression/random-scenes/{self.target.pk}/reroll/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["rerolled"] is True
        assert response.data["slot_number"] == 1
        # The new persona should be different (with enough candidates)
        assert response.data["target_persona"] != original_persona_id

    def test_reroll_twice_returns_400(self) -> None:
        """Second reroll in the same week returns 400."""
        # First reroll succeeds
        self.client.post(f"/api/progression/random-scenes/{self.target.pk}/reroll/")
        _flush_caches()
        # Create another target to try rerolling
        extra_persona, _extra_entry, _ = _make_active_character()
        extra_target = RandomSceneTarget.objects.create(
            account=self.account,
            target_persona=extra_persona,
            game_week=self.game_week,
            slot_number=2,
            first_time=False,
        )
        _flush_caches()
        response = self.client.post(f"/api/progression/random-scenes/{extra_target.pk}/reroll/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "reroll" in response.data["detail"].lower()

    def test_reroll_nonexistent_returns_404(self) -> None:
        """Rerolling a non-existent target returns 404."""
        response = self.client.post("/api/progression/random-scenes/999999/reroll/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_reroll_other_users_target_returns_404(self) -> None:
        """Cannot reroll another user's target."""
        other_user = AccountDB.objects.create_user(
            username="rs_other_reroll",
            email="rs_other_reroll@test.com",
            password="testpass123",
        )
        other_persona, _other_entry, _ = _make_active_character()
        other_target = RandomSceneTarget.objects.create(
            account=other_user,
            target_persona=other_persona,
            game_week=self.game_week,
            slot_number=1,
            first_time=False,
        )
        _flush_caches()
        response = self.client.post(f"/api/progression/random-scenes/{other_target.pk}/reroll/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_reroll_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are denied."""
        self.client.force_authenticate(user=None)
        response = self.client.post(f"/api/progression/random-scenes/{self.target.pk}/reroll/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
