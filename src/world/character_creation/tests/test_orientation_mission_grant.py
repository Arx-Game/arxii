"""Tests that finalize_character grants the orientation mission (#2479)."""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.models import Ritual
from world.missions.models import MissionTemplate
from world.seeds.character_creation import (
    ensure_durance_registration_ritual,
    ensure_orientation_mission,
)


class TestOrientationMissionSeeds(TestCase):
    def test_durance_registration_ritual_seeded(self):
        ritual = ensure_durance_registration_ritual()
        self.assertIsNotNone(ritual)
        self.assertEqual(
            ritual.service_function_path,
            "world.progression.services.durance_registration.register_durance_via_session",
        )
        self.assertTrue(Ritual.objects.filter(pk=ritual.pk).exists())

    def test_orientation_mission_seeded(self):
        template = ensure_orientation_mission()
        self.assertIsNotNone(template)
        self.assertEqual(template.name, "Orientation at Shroudwatch Academy")
        self.assertTrue(MissionTemplate.objects.filter(pk=template.pk).exists())


class TestOrientationMissionGrant(TestCase):
    def test_grant_orientation_mission_creates_instance(self):
        from world.character_creation.factories import CharacterDraftFactory
        from world.character_creation.services import _grant_orientation_mission

        draft = CharacterDraftFactory()
        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        character = sheet.character

        with patch("world.missions.services.run.staff_assign_mission") as mock_assign:
            _grant_orientation_mission(draft, character, persona)

        mock_assign.assert_called_once()
        args, kwargs = mock_assign.call_args
        self.assertEqual(args[1], character)
        self.assertEqual(kwargs["persona"], persona)
        self.assertEqual(args[0].name, "Orientation at Shroudwatch Academy")

    def test_ensure_orientation_mission_is_idempotent(self):
        first = ensure_orientation_mission()
        second = ensure_orientation_mission()
        self.assertEqual(first.pk, second.pk)
