"""DreamwalkPresence + dreamspace resolution (#3003)."""

from django.test import TestCase, override_settings

from world.conditions.models import ConditionTemplate
from world.dreams.models import DreamwalkPresence
from world.dreams.services import co_dreamers_for, dreamspace_for, end_dreamwalk, start_dreamwalk
from world.dreams.tests import DreamSleeperTestMixin
from world.vitals.constants import SLEEPING_CONDITION_NAME
from world.vitals.seeds import (
    ensure_dream_room,
    ensure_foundational_capabilities,
    ensure_sleeping_condition,
)


@override_settings(SEED_SAMPLE_CONTENT=True)
class DreamwalkPresenceTests(DreamSleeperTestMixin, TestCase):
    """Tests for DreamwalkPresence persistence and dreamspace resolution.

    Gates on SEED_SAMPLE_CONTENT (#2698) — drives the real Sleeping condition,
    same as test_dreamwalk.py/test_sleep_wake.py.
    """

    def setUp(self):
        ensure_foundational_capabilities()
        ensure_sleeping_condition()
        ensure_dream_room()
        self.template = ConditionTemplate.objects.get(name=SLEEPING_CONDITION_NAME)

    def test_dreamspace_falls_back_to_own_room(self):
        # No presence row: a sleeper perceives their own room's dreamspace.
        sheet = self._sleeping_sheet()
        assert dreamspace_for(sheet) == self._dream_room_of(sheet.character.location)

    def test_dreamspace_follows_host_when_walking(self):
        walker, host = self._two_sleepers_in_different_rooms()
        start_dreamwalk(dreamer=walker, host=host)
        assert dreamspace_for(walker) == self._dream_room_of(host.character.location)

    def test_co_dreamers_lists_host_and_visitor(self):
        walker, host = self._two_sleepers_in_different_rooms()
        start_dreamwalk(dreamer=walker, host=host)
        assert host in co_dreamers_for(walker)
        assert walker in co_dreamers_for(host)

    def test_host_wakes_visitor_falls_back(self):
        walker, host = self._two_sleepers_in_different_rooms()
        start_dreamwalk(dreamer=walker, host=host)
        self._wake(host)
        assert dreamspace_for(walker) == self._dream_room_of(walker.character.location)

    def test_end_dreamwalk_pops_row_and_returns_host_location(self):
        walker, host = self._two_sleepers_in_different_rooms()
        start_dreamwalk(dreamer=walker, host=host)
        assert end_dreamwalk(walker) == host.character.location
        assert not DreamwalkPresence.objects.filter(dreamer=walker).exists()
