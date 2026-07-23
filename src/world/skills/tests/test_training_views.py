"""Tests for the TrainingAllocationViewSet API."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from world.action_points.models import ActionPointConfig
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import PersonaFactory
from world.skills.factories import SkillFactory, SpecializationFactory
from world.skills.models import TrainingAllocation
from world.skills.views import TrainingAllocationViewSet


class TrainingAllocationViewSetTests(TestCase):
    """Cover list/create/update/delete and ownership/validation gates."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.skill = SkillFactory()
        cls.specialization = SpecializationFactory()
        cls.mentor = PersonaFactory()
        cls.weekly_regen = 100
        ActionPointConfig.objects.get_or_create(
            name="Default",
            defaults={
                "is_active": True,
                "weekly_regen": cls.weekly_regen,
            },
        )

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = TrainingAllocationViewSet.as_view(
            {
                "get": "list",
                "post": "create",
                "patch": "partial_update",
                "delete": "destroy",
            }
        )

    def _user(self, puppet):
        return SimpleNamespace(is_authenticated=True, is_staff=False, puppet=puppet)

    def _request(self, method, puppet, pk=None, data=None):
        if method == "get":
            url = "/api/skills/training-allocations/"
            request = self.factory.get(url)
        elif method == "post":
            url = "/api/skills/training-allocations/"
            request = self.factory.post(url, data, format="json")
        elif method == "patch":
            url = f"/api/skills/training-allocations/{pk}/"
            request = self.factory.patch(url, data, format="json")
        elif method == "delete":
            url = f"/api/skills/training-allocations/{pk}/"
            request = self.factory.delete(url)
        else:
            raise ValueError(method)

        force_authenticate(request, user=self._user(puppet))
        if method == "get":
            return self.view(request)
        if method == "post":
            return self.view(request)
        return self.view(request, pk=pk)

    def test_list_empty(self):
        response = self._request("get", self.character)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["allocations"], [])
        self.assertEqual(response.data["remaining_weekly_budget"], self.weekly_regen)

    def test_list_includes_allocations_and_remaining_budget(self):
        TrainingAllocation.objects.create(
            character=self.sheet,
            skill=self.skill,
            ap_amount=15,
        )
        response = self._request("get", self.character)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["allocations"]), 1)
        self.assertEqual(response.data["allocations"][0]["ap_amount"], 15)
        self.assertEqual(response.data["remaining_weekly_budget"], self.weekly_regen - 15)

    def test_create_skill_allocation(self):
        response = self._request(
            "post",
            self.character,
            data={"skill_id": self.skill.id, "ap_amount": 20},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["ap_amount"], 20)
        self.assertEqual(response.data["skill"]["id"], self.skill.id)
        self.assertTrue(
            TrainingAllocation.objects.filter(
                character=self.sheet, skill=self.skill, ap_amount=20
            ).exists()
        )

    def test_create_specialization_allocation(self):
        response = self._request(
            "post",
            self.character,
            data={"specialization_id": self.specialization.id, "ap_amount": 10},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["specialization"]["id"], self.specialization.id)

    def test_create_with_mentor(self):
        response = self._request(
            "post",
            self.character,
            data={"skill_id": self.skill.id, "ap_amount": 10, "mentor_persona_id": self.mentor.id},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["mentor"]["id"], self.mentor.id)

    def test_create_rejects_both_skill_and_specialization(self):
        response = self._request(
            "post",
            self.character,
            data={
                "skill_id": self.skill.id,
                "specialization_id": self.specialization.id,
                "ap_amount": 10,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_neither_skill_nor_specialization(self):
        response = self._request("post", self.character, data={"ap_amount": 10})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_non_positive_ap(self):
        response = self._request(
            "post",
            self.character,
            data={"skill_id": self.skill.id, "ap_amount": 0},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_exceeding_budget(self):
        TrainingAllocation.objects.create(character=self.sheet, skill=self.skill, ap_amount=60)
        other_skill = SkillFactory()
        response = self._request(
            "post",
            self.character,
            data={"skill_id": other_skill.id, "ap_amount": 50},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_unknown_skill(self):
        response = self._request(
            "post",
            self.character,
            data={"skill_id": 99999, "ap_amount": 10},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_ap_amount(self):
        allocation = TrainingAllocation.objects.create(
            character=self.sheet, skill=self.skill, ap_amount=10
        )
        response = self._request(
            "patch",
            self.character,
            pk=allocation.id,
            data={"ap_amount": 25},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        allocation.refresh_from_db()
        self.assertEqual(allocation.ap_amount, 25)

    def test_update_mentor_and_clear_mentor(self):
        allocation = TrainingAllocation.objects.create(
            character=self.sheet,
            skill=self.skill,
            ap_amount=10,
            mentor=self.mentor,
        )
        other_mentor = PersonaFactory()
        response = self._request(
            "patch",
            self.character,
            pk=allocation.id,
            data={"mentor_persona_id": other_mentor.id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        allocation.refresh_from_db()
        self.assertEqual(allocation.mentor_id, other_mentor.id)

        response = self._request(
            "patch",
            self.character,
            pk=allocation.id,
            data={"mentor_persona_id": None},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        allocation.refresh_from_db()
        self.assertIsNone(allocation.mentor_id)

    def test_update_rejects_non_positive_ap(self):
        allocation = TrainingAllocation.objects.create(
            character=self.sheet, skill=self.skill, ap_amount=10
        )
        response = self._request(
            "patch",
            self.character,
            pk=allocation.id,
            data={"ap_amount": 0},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_rejects_foreign_allocation(self):
        other_character = CharacterSheetFactory()
        foreign = TrainingAllocation.objects.create(
            character=other_character, skill=self.skill, ap_amount=10
        )
        response = self._request(
            "patch",
            self.character,
            pk=foreign.id,
            data={"ap_amount": 5},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_destroy_allocation(self):
        allocation = TrainingAllocation.objects.create(
            character=self.sheet, skill=self.skill, ap_amount=10
        )
        response = self._request(
            "delete",
            self.character,
            pk=allocation.id,
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TrainingAllocation.objects.filter(pk=allocation.id).exists())

    def test_destroy_rejects_foreign_allocation(self):
        other_character = CharacterSheetFactory()
        foreign = TrainingAllocation.objects.create(
            character=other_character, skill=self.skill, ap_amount=10
        )
        response = self._request(
            "delete",
            self.character,
            pk=foreign.id,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requires_active_puppet(self):
        request = self.factory.get("/api/skills/training-allocations/")
        force_authenticate(request, user=self._user(None))
        response = self.view(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
