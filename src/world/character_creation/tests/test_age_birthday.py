"""CG birthday + age-axis finalize tests (#2756)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.services import finalize_character
from world.character_creation.tests.test_services import DEFAULT_STATS, FinalizationTestMixin
from world.character_sheets.models import CharacterSheet, Heritage
from world.game_clock.factories import GameClockFactory
from world.game_clock.services import get_ic_now


class BirthdayFinalizeTests(FinalizationTestMixin, TestCase):
    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="birthdayuser")
        self._setup_finalization_base(self, prefix="Birthday Test", height_min=700, height_max=800)
        GameClockFactory()

    def _draft(self, **kwargs):
        draft = self._create_base_draft(first_name="Bday", stats=DEFAULT_STATS)
        for field, value in kwargs.items():
            setattr(draft, field, value)
        draft.save()
        return draft

    def test_finalize_writes_age_axes_and_birthday(self):
        draft = self._draft(birthday_month=6, birthday_day=12)
        character = finalize_character(draft, add_to_roster=True)
        sheet = CharacterSheet.objects.get(character=character)

        assert sheet.matured_years == 25
        assert sheet.withered_years == 0
        assert sheet.birthday_month == 6
        assert sheet.birthday_day == 12
        assert sheet.ic_birth_year == get_ic_now().year - 25
        assert sheet.chronological_age == 25

    def test_sleeper_heritage_leaves_birth_year_unknown(self):
        sleeper = Heritage.objects.create(
            name="Sleeper",
            is_special=True,
            family_known=False,
            chronological_age_unknown=True,
        )
        self.beginnings.heritage = sleeper
        self.beginnings.save()

        draft = self._draft(birthday_month=1, birthday_day=1)
        character = finalize_character(draft, add_to_roster=True)
        sheet = CharacterSheet.objects.get(character=character)

        assert sheet.ic_birth_year is None
        assert sheet.chronological_age is None
        assert sheet.matured_years == 25  # waking-day age still real
