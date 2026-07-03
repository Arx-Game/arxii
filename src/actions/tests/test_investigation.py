"""SearchAction (#1154 slice B) — the search command's wrapper over search_room."""

from unittest.mock import patch

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

    def test_search_detects_a_concealed_character(self) -> None:
        from world.conditions.factories import (
            ConditionCategoryFactory,
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.services import can_perceive

        target_roster = RosterEntryFactory()
        target = target_roster.character_sheet.character
        target.move_to(self.room, quiet=True)
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        tmpl = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=target, condition=tmpl)

        self.assertFalse(can_perceive(self.actor, target))

        with force_check_outcome(self.success):
            SearchAction().execute(self.actor)

        self.assertTrue(can_perceive(self.actor, target))

    def test_search_success_refreshes_detecting_actor_room_state(self) -> None:
        """A successful detection must push a room_state refresh (#1225) so the
        newly-detected character shows up without waiting for the next natural
        room_state event."""
        from world.conditions.factories import (
            ConditionCategoryFactory,
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )

        target_roster = RosterEntryFactory()
        target = target_roster.character_sheet.character
        target.move_to(self.room, quiet=True)
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        tmpl = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=target, condition=tmpl)

        with (
            force_check_outcome(self.success),
            patch.object(self.actor, "send_room_state") as mock_send,
        ):
            SearchAction().execute(self.actor)

        mock_send.assert_called_once()

    def test_search_without_detection_does_not_refresh_room_state(self) -> None:
        """No concealed characters present — nothing to detect, so no refresh."""
        with patch.object(self.actor, "send_room_state") as mock_send:
            SearchAction().execute(self.actor)

        mock_send.assert_not_called()
