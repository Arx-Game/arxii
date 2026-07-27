"""Three-axis age model tests (#2756).

Chronological derives from the game clock; biological = matured + withered;
apparent = biological (cosmetic overrides live in the appearance layer).
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import Heritage
from world.game_clock.factories import GameClockFactory
from world.game_clock.services import get_ic_now


class AgeAxesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory(matured_years=30, withered_years=10)

    def test_biological_is_matured_plus_withered(self):
        self.assertEqual(self.sheet.biological_age, 40)

    def test_apparent_defaults_to_biological(self):
        self.assertEqual(self.sheet.apparent_age, 40)

    def test_chronological_derives_from_clock(self):
        GameClockFactory()
        current_year = get_ic_now().year
        self.sheet.ic_birth_year = current_year - 1000
        self.assertEqual(self.sheet.chronological_age, 1000)

    def test_chronological_none_when_birth_year_unknown(self):
        GameClockFactory()
        self.sheet.ic_birth_year = None
        self.assertIsNone(self.sheet.chronological_age)

    def test_chronological_none_without_clock(self):
        self.sheet.ic_birth_year = 100
        self.assertIsNone(self.sheet.chronological_age)

    def test_birthday_pair_validates_real_dates(self):
        self.sheet.birthday_month = 2
        self.sheet.birthday_day = 30
        with self.assertRaises(ValidationError):
            self.sheet.full_clean()

    def test_birthday_pair_accepts_leap_day(self):
        self.sheet.birthday_month = 2
        self.sheet.birthday_day = 29
        self.sheet.full_clean()

    def test_heritage_chronological_age_unknown_flag(self):
        heritage = Heritage.objects.create(name="Sleeper (test)", chronological_age_unknown=True)
        self.assertTrue(heritage.chronological_age_unknown)

    def test_retired_fields_are_gone(self):
        for retired in ("age", "real_age", "birthday"):
            with self.subTest(field=retired):
                self.assertFalse(
                    any(f.name == retired for f in self.sheet._meta.get_fields()),
                    f"{retired} should be removed from CharacterSheet",
                )
