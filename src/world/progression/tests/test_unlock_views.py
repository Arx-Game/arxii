"""Tests for the progression unlock shop API."""

from types import SimpleNamespace
from typing import cast

from django.test import TestCase
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.magic.factories import ThreadFactory, ThreadXPLockedLevelFactory
from world.magic.models import ThreadLevelUnlock
from world.progression.factories import ExperiencePointsDataFactory
from world.progression.models import (
    CharacterUnlock,
    ClassLevelUnlock,
    ClassXPCost,
    TraitRatingUnlock,
    TraitXPCost,
    XPCostChart,
    XPCostEntry,
)
from world.skills.factories import CharacterSkillValueFactory, SkillFactory


class UnlockShopViewTests(TestCase):
    """Tests for GET /api/progression/unlocks/ and POST /api/progression/unlocks/purchase/."""

    @classmethod
    def setUpTestData(cls):
        cls.account: AccountDB = AccountFactory(
            username="unlocktester",
            email="unlock@example.com",
        )
        cls.sheet = CharacterSheetFactory()
        cls.character = cast(ObjectDB, cls.sheet.character)
        cls.character.db_account = cls.account
        cls.character.save()

    def setUp(self):
        fake_user = SimpleNamespace(
            is_authenticated=True,
            is_staff=False,
            puppet=self.character,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=fake_user)  # type: ignore[arg-type]

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

    def _create_gated_skill(self, *, xp_cost: int | None = None):
        """Create a skill parked at an XP boundary (#2115), optionally with an authored cost."""
        skill = SkillFactory()
        CharacterSkillValueFactory(character=self.character, skill=skill, value=19)
        if xp_cost is not None:
            chart = XPCostChart.objects.create(name=f"Breakthrough Chart {skill.pk}")
            XPCostEntry.objects.create(chart=chart, level=20, xp_cost=xp_cost)
            TraitXPCost.objects.create(trait=skill.trait, cost_chart=chart)
            TraitRatingUnlock.objects.create(trait=skill.trait, target_rating=20)
        return skill

    def test_list_includes_class_level_and_thread_xp_lock_items(self):
        """GET returns both class-level and thread XP-lock unlock items."""
        class_unlock = self._create_class_level_unlock(xp_cost=100)
        thread = self._create_near_thread()

        response = self.client.get("/api/progression/unlocks/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        types = {item["unlock_type"] for item in results}
        self.assertIn("class_level", types)
        self.assertIn("thread_xp_lock", types)

        class_item = next(item for item in results if item["unlock_type"] == "class_level")
        self.assertEqual(class_item["class_level_unlock_id"], class_unlock.pk)
        self.assertEqual(class_item["xp_cost"], 100)
        self.assertTrue(class_item["requirements_met"])
        self.assertIsNone(class_item["locked_reason"])

        thread_item = next(item for item in results if item["unlock_type"] == "thread_xp_lock")
        self.assertEqual(thread_item["thread_id"], thread.pk)
        self.assertEqual(thread_item["boundary_level"], 10)
        self.assertEqual(thread_item["xp_cost"], 100)

    def test_list_is_paginated(self):
        """GET returns a paginated wrapper by default."""
        self._create_class_level_unlock(xp_cost=100)
        self._create_class_level_unlock(xp_cost=200)

        response = self.client.get("/api/progression/unlocks/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertIn("count", response.data)
        self.assertEqual(response.data["count"], 2)

    def test_list_filters_by_unlock_type(self):
        """GET with unlock_type only returns matching items."""
        class_unlock = self._create_class_level_unlock(xp_cost=100)
        self._create_near_thread()

        response = self.client.get("/api/progression/unlocks/?unlock_type=class_level")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["unlock_type"], "class_level")
        self.assertEqual(results[0]["class_level_unlock_id"], class_unlock.pk)

    def test_list_requires_played_character(self):
        """Listing unlocks fails when the request has no played character."""
        fake_user = SimpleNamespace(is_authenticated=True, is_staff=False, puppet=None)
        self.client.force_authenticate(user=fake_user)
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
                character=self.sheet,
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
                character=self.sheet,
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

    def test_list_includes_skill_breakthrough_item(self):
        """GET includes an authored skill_breakthrough item for a gated skill (#2115)."""
        skill = self._create_gated_skill(xp_cost=75)

        response = self.client.get("/api/progression/unlocks/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        item = next(i for i in results if i["unlock_type"] == "skill_breakthrough")
        self.assertEqual(item["skill_id"], skill.pk)
        self.assertEqual(item["xp_cost"], 75)
        self.assertTrue(item["requirements_met"])
        self.assertIsNone(item["locked_reason"])

    def test_list_marks_unauthored_skill_breakthrough_as_locked(self):
        """An unauthored breakthrough surfaces as not-yet-purchasable, not silently absent."""
        skill = self._create_gated_skill(xp_cost=None)

        response = self.client.get("/api/progression/unlocks/")

        results = response.data["results"]
        item = next(i for i in results if i["unlock_type"] == "skill_breakthrough")
        self.assertEqual(item["skill_id"], skill.pk)
        self.assertFalse(item["requirements_met"])
        self.assertEqual(item["locked_reason"], "Not yet authored")

    def test_purchase_skill_breakthrough_success(self):
        """POST purchase can buy a skill breakthrough when XP is available (#2115)."""
        skill = self._create_gated_skill(xp_cost=100)
        self._set_xp(150)

        response = self.client.post(
            "/api/progression/unlocks/purchase/",
            {"unlock_type": "skill_breakthrough", "skill_id": skill.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unlock_type"], "skill_breakthrough")
        self.assertEqual(response.data["skill_id"], skill.pk)

    def test_purchase_skill_breakthrough_insufficient_xp(self):
        """POST purchase fails with 400 when XP is insufficient for a skill breakthrough."""
        skill = self._create_gated_skill(xp_cost=100)
        self._set_xp(50)

        response = self.client.post(
            "/api/progression/unlocks/purchase/",
            {"unlock_type": "skill_breakthrough", "skill_id": skill.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
