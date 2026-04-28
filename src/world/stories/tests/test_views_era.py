"""Tests for EraViewSet — list / detail / advance / archive actions."""

from django.test import TestCase
from rest_framework.test import APIClient

from world.stories.constants import EraStatus
from world.stories.factories import EraFactory, StoryFactory


class EraViewSetSetup(TestCase):
    """Shared setUp for EraViewSet tests."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        # Staff user
        cls.staff_user = AccountDB.objects.create_user(
            username="staff_era_test",
            password="test",
            email="staff_era@test.com",
        )
        cls.staff_user.is_staff = True
        cls.staff_user.is_superuser = True
        cls.staff_user.save()

        # Regular player
        cls.player_user = AccountDB.objects.create_user(
            username="player_era_test",
            password="test",
            email="player_era@test.com",
        )

    def setUp(self) -> None:
        self.client = APIClient()

    def _staff_client(self) -> APIClient:
        c = APIClient()
        c.force_authenticate(user=self.staff_user)
        return c

    def _player_client(self) -> APIClient:
        c = APIClient()
        c.force_authenticate(user=self.player_user)
        return c


class EraListTests(EraViewSetSetup):
    """List endpoint accessibility."""

    def test_staff_can_list_eras(self) -> None:
        EraFactory(name="s1_list_staff")
        res = self._staff_client().get("/api/eras/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("results", res.json())

    def test_player_can_list_eras(self) -> None:
        """Eras are public metaplot info — any authenticated user can read."""
        EraFactory(name="s1_list_player")
        res = self._player_client().get("/api/eras/")
        self.assertEqual(res.status_code, 200)

    def test_unauthenticated_cannot_list_eras(self) -> None:
        res = self.client.get("/api/eras/")
        self.assertEqual(res.status_code, 403)


class EraWritePermissionTests(EraViewSetSetup):
    """Write operations require staff."""

    def test_player_cannot_create_era(self) -> None:
        res = self._player_client().post(
            "/api/eras/",
            {"name": "s99", "display_name": "Season 99", "season_number": 99},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_staff_can_create_era(self) -> None:
        res = self._staff_client().post(
            "/api/eras/",
            {
                "name": "new_era_create",
                "display_name": "New Era",
                "season_number": 77,
                "status": EraStatus.UPCOMING,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)

    def test_player_cannot_delete_era(self) -> None:
        era = EraFactory(name="s_delete_test")
        res = self._player_client().delete(f"/api/eras/{era.pk}/")
        self.assertEqual(res.status_code, 403)


class EraAdvanceActionTests(EraViewSetSetup):
    """POST /api/eras/{id}/advance/ — staff only."""

    def test_staff_can_advance_upcoming_era(self) -> None:
        upcoming = EraFactory(status=EraStatus.UPCOMING, name="s_adv_upcoming")
        res = self._staff_client().post(f"/api/eras/{upcoming.pk}/advance/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], EraStatus.ACTIVE)

    def test_advance_closes_current_active_era(self) -> None:
        active = EraFactory(status=EraStatus.ACTIVE, name="s_adv_active")
        upcoming = EraFactory(status=EraStatus.UPCOMING, name="s_adv_upcoming2")
        self._staff_client().post(f"/api/eras/{upcoming.pk}/advance/")
        active.refresh_from_db()
        self.assertEqual(active.status, EraStatus.CONCLUDED)

    def test_player_cannot_advance_era(self) -> None:
        upcoming = EraFactory(status=EraStatus.UPCOMING, name="s_player_adv")
        res = self._player_client().post(f"/api/eras/{upcoming.pk}/advance/")
        self.assertEqual(res.status_code, 403)

    def test_cannot_advance_active_era(self) -> None:
        active = EraFactory(status=EraStatus.ACTIVE, name="s_cant_adv_active")
        res = self._staff_client().post(f"/api/eras/{active.pk}/advance/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("detail", res.json())

    def test_cannot_advance_concluded_era(self) -> None:
        concluded = EraFactory(status=EraStatus.CONCLUDED, name="s_cant_adv_concluded")
        res = self._staff_client().post(f"/api/eras/{concluded.pk}/advance/")
        self.assertEqual(res.status_code, 400)


class EraArchiveActionTests(EraViewSetSetup):
    """POST /api/eras/{id}/archive/ — staff only."""

    def test_staff_can_archive_active_era(self) -> None:
        era = EraFactory(status=EraStatus.ACTIVE, name="s_arch_active")
        res = self._staff_client().post(f"/api/eras/{era.pk}/archive/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], EraStatus.CONCLUDED)

    def test_staff_can_archive_concluded_era_idempotent(self) -> None:
        era = EraFactory(status=EraStatus.CONCLUDED, name="s_arch_concluded")
        res = self._staff_client().post(f"/api/eras/{era.pk}/archive/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], EraStatus.CONCLUDED)

    def test_player_cannot_archive_era(self) -> None:
        era = EraFactory(status=EraStatus.ACTIVE, name="s_player_arch")
        res = self._player_client().post(f"/api/eras/{era.pk}/archive/")
        self.assertEqual(res.status_code, 403)

    def test_cannot_archive_upcoming_era(self) -> None:
        era = EraFactory(status=EraStatus.UPCOMING, name="s_cant_arch_upcoming")
        res = self._staff_client().post(f"/api/eras/{era.pk}/archive/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("detail", res.json())


class EraStoryCountTests(EraViewSetSetup):
    """story_count field reflects Story.created_in_era relationship."""

    def test_story_count_correct(self) -> None:
        era = EraFactory(status=EraStatus.ACTIVE, name="s_story_count")
        # Two stories created in this era
        StoryFactory(created_in_era=era)
        StoryFactory(created_in_era=era)
        # One story in a different era
        other_era = EraFactory(status=EraStatus.UPCOMING, name="s_other")
        StoryFactory(created_in_era=other_era)

        res = self._player_client().get(f"/api/eras/{era.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["story_count"], 2)

    def test_story_count_zero_when_no_stories(self) -> None:
        era = EraFactory(status=EraStatus.UPCOMING, name="s_zero_count")
        res = self._player_client().get(f"/api/eras/{era.pk}/")
        self.assertEqual(res.json()["story_count"], 0)


class EraFilterTests(EraViewSetSetup):
    """EraFilter works correctly via the API."""

    def test_filter_by_status(self) -> None:
        EraFactory(status=EraStatus.UPCOMING, name="s_filter_upcoming")
        EraFactory(status=EraStatus.ACTIVE, name="s_filter_active")
        EraFactory(status=EraStatus.CONCLUDED, name="s_filter_concluded")

        res = self._player_client().get("/api/eras/?status=upcoming")
        data = res.json()
        statuses = [r["status"] for r in data["results"]]
        self.assertTrue(all(s == EraStatus.UPCOMING for s in statuses))

    def test_filter_by_season_number(self) -> None:
        era = EraFactory(name="s_filter_season_999", season_number=999)
        res = self._player_client().get("/api/eras/?season_number=999")
        self.assertEqual(res.json()["count"], 1)
        self.assertEqual(res.json()["results"][0]["id"], era.pk)
