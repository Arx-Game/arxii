"""SearchAction (#1154 slice B) — the search command's wrapper over search_room."""

from unittest.mock import patch

from django.test import TestCase

from actions.constants import ActionCategory
from actions.definitions.investigation import SearchAction
from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from actions.registry import get_action
from evennia_extensions.factories import RoomProfileFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.constants import SEARCH_CHECK_TYPE_NAME
from world.clues.factories import RoomClueFactory
from world.conditions.factories import DamageTypeFactory
from world.room_features.factories import TrapFactory
from world.roster.factories import RosterEntryFactory
from world.traits.factories import CheckOutcomeFactory
from world.vitals.factories import CharacterVitalsFactory


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

    def test_search_reports_a_detected_trap(self) -> None:
        """A hidden armed trap in the room rides the search's message (#3011)."""
        trap = TrapFactory(
            room_profile=self.room_profile,
            detect_check_type=CheckTypeFactory(name="Detect Traps"),
        )

        with force_check_outcome(self.success):
            result = SearchAction().execute(self.actor)

        assert result.success
        assert trap.name in result.message
        assert self.actor.character_sheet in trap.detected_by.all()

    def test_search_does_not_report_a_missed_trap(self) -> None:
        """A failed trap-search roll leaves the trap undetected and unfired (#3011)."""
        miss = CheckOutcomeFactory(name="SearchMiss", success_level=-1)
        trap = TrapFactory(
            room_profile=self.room_profile,
            detect_check_type=CheckTypeFactory(name="Detect Traps"),
        )

        with force_check_outcome(miss):
            result = SearchAction().execute(self.actor)

        assert result.success
        assert trap.name not in result.message
        assert "nothing" in result.message.lower()
        assert self.actor.character_sheet not in trap.detected_by.all()


class SearchThenDisarmJourneyTest(TestCase):
    """End-to-end player trap loop (#3011): search finds a hidden trap, then a
    later ``disarm_trap`` dispatch either succeeds cleanly or fires the trap on
    the would-be disarmer. Exercises the same seam telnet and web both dispatch
    through (``action.run()``), not ``SearchAction``/``DisarmTrapAction``
    internals directly.
    """

    def setUp(self) -> None:
        CheckTypeFactory(name=SEARCH_CHECK_TYPE_NAME)
        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb
        roster = RosterEntryFactory()
        self.sheet = roster.character_sheet
        self.actor = self.sheet.character
        self.actor.move_to(self.room, quiet=True)
        self.vitals = CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)

        self.detect_hit = CheckOutcomeFactory(name="Journey-Detect-Hit", success_level=1)
        self.disarm_success = CheckOutcomeFactory(name="Journey-Disarm-Success", success_level=1)
        self.disarm_failure = CheckOutcomeFactory(name="Journey-Disarm-Failure", success_level=0)

        pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory(outcome_tier=self.disarm_failure, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.DEAL_DAMAGE,
            target=EffectTarget.SELF,
            damage_amount=25,
            damage_type=DamageTypeFactory(name="journey-trap-spikes"),
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        self.trap = TrapFactory(
            room_profile=self.room_profile,
            consequence_pool=pool,
            detect_check_type=CheckTypeFactory(name="Journey Detect Traps"),
            disarm_check_type=CheckTypeFactory(name="Journey Disarm Traps"),
            detect_difficulty=10,
            disarm_difficulty=10,
        )

    def _health(self) -> int:
        self.vitals.refresh_from_db()
        return self.vitals.health

    def _search(self) -> None:
        with force_check_outcome(self.detect_hit):
            result = SearchAction().execute(self.actor)
        assert self.trap.name in result.message
        assert self.sheet in self.trap.detected_by.all()

    def test_search_then_successful_disarm(self) -> None:
        self._search()

        action = get_action("disarm_trap")
        with force_check_outcome(self.disarm_success):
            disarm_result = action.run(self.actor, trap_id=self.trap.pk)

        assert disarm_result.success is True
        self.trap.refresh_from_db()
        assert self.trap.is_armed is False
        assert self._health() == 100

    def test_search_then_failed_disarm_fires_the_trap_on_the_disarmer(self) -> None:
        self._search()

        action = get_action("disarm_trap")
        with force_check_outcome(self.disarm_failure):
            disarm_result = action.run(self.actor, trap_id=self.trap.pk)

        assert disarm_result.success is False
        assert self.trap.name in disarm_result.message
        self.trap.refresh_from_db()
        assert self.trap.is_armed is True
        assert self._health() == 75
