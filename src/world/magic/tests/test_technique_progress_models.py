"""Tests for TechniqueProgress + TechniqueProgressWeekly models (#2711)."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.game_clock.week_services import get_current_game_week
from world.magic.factories import TechniqueFactory
from world.magic.models import (
    TechniqueProgress,
    TechniqueProgressWeekly,
)
from world.roster.factories import RosterTenureFactory


class TechniqueProgressModelTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory()

    def test_create_progress(self):
        progress = TechniqueProgress.objects.create(
            character_sheet=self.sheet,
            technique=self.technique,
            total_required=50,
            source="gift_acquisition",
        )
        self.assertEqual(progress.points_accumulated, 0)
        self.assertEqual(progress.total_required, 50)
        self.assertFalse(progress.is_cross_path)
        self.assertIsNone(progress.teacher_tenure)

    def test_unique_per_character_technique(self):
        TechniqueProgress.objects.create(
            character_sheet=self.sheet,
            technique=self.technique,
            total_required=50,
            source="gift_acquisition",
        )
        with self.assertRaises(IntegrityError):
            TechniqueProgress.objects.create(
                character_sheet=self.sheet,
                technique=self.technique,
                total_required=100,
                source="gift_acquisition",
            )

    def test_with_teacher_tenure(self):
        tenure = RosterTenureFactory()
        progress = TechniqueProgress.objects.create(
            character_sheet=self.sheet,
            technique=self.technique,
            total_required=100,
            source="gift_acquisition",
            teacher_tenure=tenure,
            is_cross_path=True,
        )
        self.assertEqual(progress.teacher_tenure, tenure)
        self.assertTrue(progress.is_cross_path)


class TechniqueProgressWeeklyModelTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory()
        self.game_week = get_current_game_week()

    def test_create_weekly(self):
        weekly = TechniqueProgressWeekly.objects.create(
            character_sheet=self.sheet,
            technique=self.technique,
            game_week=self.game_week,
            points_contributed=20,
        )
        self.assertEqual(weekly.points_contributed, 20)

    def test_unique_per_character_technique_week(self):
        TechniqueProgressWeekly.objects.create(
            character_sheet=self.sheet,
            technique=self.technique,
            game_week=self.game_week,
            points_contributed=10,
        )
        with self.assertRaises(IntegrityError):
            TechniqueProgressWeekly.objects.create(
                character_sheet=self.sheet,
                technique=self.technique,
                game_week=self.game_week,
                points_contributed=20,
            )
