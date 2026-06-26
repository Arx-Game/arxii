"""Tests for the progression unlock shop API."""

from types import SimpleNamespace

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework import status
from rest_framework.test import APIClient

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.magic.factories import ThreadFactory, ThreadXPLockedLevelFactory
from world.magic.models import ThreadLevelUnlock
from world.progression.factories import ExperiencePointsDataFactory
from world.progression.models import (
    CharacterUnlock,
    ClassLevelUnlock,
    ClassXPCost,
    XPCostChart,
    XPCostEntry,
)


class UnlockShopViewTests(TestCase):
    """Tests for GET /api/progression/unlocks/ and POST /api/progression/unlocks/purchase/."""

    def setUp(self):
        self.account = AccountDB.objects.create_user(
            username="unlocktester",
            email="unlock@example.com",
            password="testpass123",
        )
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.db_account = self.account
        self.character.save()

        self.client = APIClient()
        self.client.force_authenticate(
            user=SimpleNamespace(
                is_authenticated=True,
                is_staff=False,
                puppet=self.character,
            ),
        )

    def _create_class_level_unlock(self, *, xp_cost: int):
        """Create a class-level unlock with an XP cost chart."""
        class_level = CharacterClassLevelFactory(character=self.character, level=3)
        class_unlock = ClassLevelUnlock.objects.create(
            character_class=class_level.character_class,
            target_level=4,
        )
        chart = XPCostChart.objects.create(name=f"Test Chart {class_unlock.pk}")
        XPCostEntry.objects.create(chart=chart, level=4, xp_cost=xp_cost)
        ClassXPCost.objects.create(
            character_class=class_level.character_class,
            cost_chart=chart,
        )
        return class_unlock

    def _set_xp(self, total_earned: int, total_spent: int = 0):
        """Set the account's available XP."""
        ExperiencePointsDataFactory(
            account=self.account,
            total_earned=total_earned,
            total_spent=total_spent,
        )

    def _create_near_thread(self):
        """Create an owned thread with a nearby XP-lock boundary."""
        ThreadXPLockedLevelFactory(level=10, xp_cost=100)
        return ThreadFactory(
            owner=self.sheet,
            level=0,
            developed_points=10,
            _trait_value=30,
            _path_stage=2,
        )

    def test_list_includes_class_level_and_thread_xp_lock_items(self):
        """GET returns both class-level and thread XP-lock unlock items."""
        class_unlock = self._create_class_level_unlock(xp_cost=100)
        thread = self._create_near_thread()

        response = self.client.get("/api/progression/unlocks/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        unlocks = response.data["unlocks"]
        types = {item["unlock_type"] for item in unlocks}
        self.assertIn("class_level", types)
        self.assertIn("thread_xp_lock", types)

        class_item = next(item for item in unlocks if item["unlock_type"] == "class_level")
        self.assertEqual(class_item["class_level_unlock_id"], class_unlock.pk)
        self.assertEqual(class_item["xp_cost"], 100)
        self.assertTrue(class_item["requirements_met"])
        self.assertIsNone(class_item["locked_reason"])

        thread_item = next(item for item in unlocks if item["unlock_type"] == "thread_xp_lock")
        self.assertEqual(thread_item["thread_id"], thread.pk)
        self.assertEqual(thread_item["boundary_level"], 10)
        self.assertEqual(thread_item["xp_cost"], 100)

    def test_list_requires_played_character(self):
        """Listing unlocks fails when the request has no played character."""
        self.client.force_authenticate(
            user=SimpleNamespace(is_authenticated=True, is_staff=False, puppet=None),
        )
        response = self.client.get("/api/progression/unlocks/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_purchase_class_level_unlock_success(self):
        """POST purchase can buy a class-level unlock when XP is available."""
        class_unlock = self._create_class_level_unlock(xp_cost=100)
        self._set_xp(150)

        response = self.client.post(
            "/api/progression/unlocks/purchase/",
            {
                "unlock_type": "class_level",
                "class_level_unlock_id": class_unlock.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unlock_type"], "class_level")
        self.assertTrue(
            CharacterUnlock.objects.filter(
                character=self.character,
                character_class=class_unlock.character_class,
                target_level=4,
            ).exists()
        )

    def test_purchase_class_level_unlock_insufficient_xp(self):
        """POST purchase fails with 400 when the account lacks enough XP."""
        class_unlock = self._create_class_level_unlock(xp_cost=100)
        self._set_xp(50)

        response = self.client.post(
            "/api/progression/unlocks/purchase/",
            {
                "unlock_type": "class_level",
                "class_level_unlock_id": class_unlock.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            CharacterUnlock.objects.filter(
                character=self.character,
                character_class=class_unlock.character_class,
                target_level=4,
            ).exists()
        )

    def test_purchase_thread_xp_lock_success(self):
        """POST purchase can buy a thread XP-lock boundary the actor owns."""
        thread = self._create_near_thread()
        self._set_xp(150)

        response = self.client.post(
            "/api/progression/unlocks/purchase/",
            {
                "unlock_type": "thread_xp_lock",
                "thread_id": thread.pk,
                "boundary_level": 10,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unlock_type"], "thread_xp_lock")
        self.assertEqual(response.data["thread_id"], thread.pk)
        self.assertEqual(response.data["boundary_level"], 10)
        self.assertTrue(
            ThreadLevelUnlock.objects.filter(
                thread=thread,
                unlocked_level=10,
            ).exists()
        )

    def test_purchase_thread_xp_lock_insufficient_xp(self):
        """POST purchase fails with 400 when XP is insufficient for a thread lock."""
        thread = self._create_near_thread()
        self._set_xp(50)

        response = self.client.post(
            "/api/progression/unlocks/purchase/",
            {
                "unlock_type": "thread_xp_lock",
                "thread_id": thread.pk,
                "boundary_level": 10,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            ThreadLevelUnlock.objects.filter(
                thread=thread,
                unlocked_level=10,
            ).exists()
        )

    def test_unauthenticated_requests_are_denied(self):
        """Unauthenticated clients cannot access the unlock shop."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/progression/unlocks/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
