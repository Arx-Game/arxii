"""Phase D D4.3: staff-power actions.

- POST /api/missions/templates/<slug>/assign/ — drop a mission on a
  character, bypassing availability filters.
- DELETE /api/missions/instances/<id>/ — remove a stuck instance.
- GET /api/missions/instances/ + retrieve — staff visibility.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.missions.constants import MissionStatus
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionInstance, MissionParticipant


class AssignActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-assign", is_staff=True)
        cls.template = MissionTemplateFactory(slug="assign-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="assign-entry", is_entry=True)
        cls.character = CharacterFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_assign_creates_instance(self) -> None:
        response = self.client.post(
            f"/api/missions/templates/{self.template.slug}/assign/",
            {"character": self.character.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        instance_id = response.data["id"]
        self.assertTrue(MissionInstance.objects.filter(pk=instance_id).exists())

    def test_assign_creates_contract_holder_participant(self) -> None:
        response = self.client.post(
            f"/api/missions/templates/{self.template.slug}/assign/",
            {"character": self.character.pk},
            format="json",
        )
        instance_id = response.data["id"]
        participant = MissionParticipant.objects.get(instance_id=instance_id)
        self.assertEqual(participant.character_id, self.character.pk)
        self.assertTrue(participant.is_contract_holder)

    def test_assign_sets_current_node_to_entry(self) -> None:
        response = self.client.post(
            f"/api/missions/templates/{self.template.slug}/assign/",
            {"character": self.character.pk},
            format="json",
        )
        self.assertEqual(response.data["current_node"], self.entry.pk)
        self.assertEqual(response.data["status"], MissionStatus.ACTIVE)

    def test_assign_requires_character_id(self) -> None:
        response = self.client.post(
            f"/api/missions/templates/{self.template.slug}/assign/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assign_404_when_character_missing(self) -> None:
        response = self.client.post(
            f"/api/missions/templates/{self.template.slug}/assign/",
            {"character": 999_999_999},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class InstanceRemoveTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-rmi", is_staff=True)
        cls.template = MissionTemplateFactory(slug="rmi-tmpl")
        cls.instance = MissionInstanceFactory(template=cls.template)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_destroy_removes_instance(self) -> None:
        url = f"/api/missions/instances/{self.instance.pk}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(MissionInstance.objects.filter(pk=self.instance.pk).exists())

    def test_retrieve_returns_shape(self) -> None:
        # Use a fresh instance to avoid any savepoint-rollback / identity-map
        # interaction with destroy test (which targets self.instance).
        instance = MissionInstanceFactory(template=self.template)
        url = f"/api/missions/instances/{instance.pk}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["template"], self.template.pk)

    def test_list_paginated(self) -> None:
        response = self.client.get("/api/missions/instances/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)

    def test_no_post_endpoint(self) -> None:
        # Create-via-POST not supported on this viewset; instance creation
        # is the staff-assign action on the template viewset (D4.3 assign).
        response = self.client.post(
            "/api/missions/instances/",
            {"template": self.template.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
