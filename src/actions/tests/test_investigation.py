"""SearchAction (#1154 slice B) — the search command's wrapper over search_room."""

from django.test import TestCase

from actions.constants import ActionCategory
from actions.definitions.investigation import SearchAction
from actions.registry import get_action
from evennia_extensions.factories import RoomProfileFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.factories import RoomClueFactory
from world.roster.factories import RosterEntryFactory
from world.traits.factories import CheckOutcomeFactory


class SearchActionTests(TestCase):
    def setUp(self) -> None:
        self.search_check = CheckTypeFactory(name="Search")
        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb
        roster = RosterEntryFactory()
        self.actor = roster.character_sheet.character
        self.actor.move_to(self.room, quiet=True)
        self.success = CheckOutcomeFactory(name="SearchHit", success_level=3)

    def test_registered_with_declarative_cost(self) -> None:
        action = get_action("search")
        assert isinstance(action, SearchAction)
        assert action.ap_cost > 0
        assert action.fatigue_cost > 0
        assert action.fatigue_category == ActionCategory.MENTAL

    def test_search_reports_a_found_clue(self) -> None:
        placement = RoomClueFactory(room_profile=self.room_profile)

        with force_check_outcome(self.success):
            result = SearchAction().execute(self.actor)

        assert result.success
        assert placement.clue.name in result.message

    def test_search_empty_room_reports_nothing(self) -> None:
        result = SearchAction().execute(self.actor)

        assert result.success
        assert "nothing" in result.message.lower()
