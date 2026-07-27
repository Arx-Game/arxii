"""Town Crier birthday digest (#2756): merge-on-read tidings source."""

from datetime import timedelta

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.types import ActivityState, LifecycleState
from world.game_clock.factories import GameClockFactory
from world.game_clock.services import get_ic_now
from world.roster.factories import RosterEntryFactory, RosterFactory
from world.roster.models.choices import RosterType
from world.tidings.constants import FeedItemKind
from world.tidings.services import hub_feed_for_room


class BirthdayFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        GameClockFactory()
        cls.room_profile = RoomProfileFactory()
        cls.room = cls.room_profile.objectdb
        cls.active_roster = RosterFactory(name="Active", roster_type=RosterType.ACTIVE)
        cls.npc_roster = RosterFactory(name="NPC Shelf", roster_type=RosterType.NPC)

    def _entry(self, *, days_ahead=3, roster=None, **sheet_updates):
        ic_now = get_ic_now()
        bday = ic_now + timedelta(days=days_ahead)
        entry = RosterEntryFactory(roster=roster or self.active_roster)
        sheet = entry.character_sheet
        sheet.birthday_month = bday.month
        sheet.birthday_day = bday.day
        for field, value in sheet_updates.items():
            setattr(sheet, field, value)
        sheet.save()
        return entry

    def _birthday_items(self):
        return [item for item in hub_feed_for_room(self.room) if item.kind == FeedItemKind.BIRTHDAY]

    def test_upcoming_birthday_of_active_character_is_listed(self):
        entry = self._entry(days_ahead=3)
        items = self._birthday_items()
        self.assertEqual(len(items), 1)
        self.assertIn(entry.character_sheet.character.db_key, items[0].headline)

    def test_birthday_beyond_the_window_is_not_listed(self):
        self._entry(days_ahead=40)
        self.assertEqual(self._birthday_items(), [])

    def test_dead_and_dormant_characters_are_excluded(self):
        self._entry(days_ahead=3, lifecycle_state=LifecycleState.DEAD)
        self._entry(days_ahead=3, activity_state=ActivityState.INACTIVE)
        self.assertEqual(self._birthday_items(), [])

    def test_non_active_roster_is_excluded(self):
        self._entry(days_ahead=3, roster=self.npc_roster)
        self.assertEqual(self._birthday_items(), [])
