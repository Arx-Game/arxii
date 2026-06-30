from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.progression.models import DuranceTrainingSite


class DuranceTrainingSiteTests(TestCase):
    def setUp(self) -> None:
        self.room = RoomProfileFactory()
        self.trainer = CharacterSheetFactory()

    def test_create_and_str(self) -> None:
        site = DuranceTrainingSite.objects.create(
            room_profile=self.room,
            officiant=self.trainer,
            training_path=PathFactory(stage=PathStage.PROSPECT),
        )
        self.assertTrue(site.is_active)
        self.assertEqual(site.officiant, self.trainer)

    def test_unique_room_officiant(self) -> None:
        DuranceTrainingSite.objects.create(room_profile=self.room, officiant=self.trainer)
        with self.assertRaises(IntegrityError):
            DuranceTrainingSite.objects.create(room_profile=self.room, officiant=self.trainer)
