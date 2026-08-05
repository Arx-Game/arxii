"""DreamwalkPresence + dreamspace resolution (#3003)."""

from django.test import TestCase, override_settings

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.character_sheets.models import CharacterSheet
from world.character_sheets.services import create_character_with_sheet
from world.conditions.models import ConditionTemplate
from world.conditions.services import apply_condition, remove_condition
from world.dreams.models import DreamReflection, DreamwalkPresence
from world.dreams.services import (
    co_dreamers_for,
    dreamspace_for,
    end_dreamwalk,
    get_dream_space,
    start_dreamwalk,
)
from world.vitals.constants import SLEEPING_CONDITION_NAME
from world.vitals.seeds import (
    ensure_dream_room,
    ensure_foundational_capabilities,
    ensure_sleeping_condition,
)


@override_settings(SEED_SAMPLE_CONTENT=True)
class DreamwalkPresenceTests(TestCase):
    """Tests for DreamwalkPresence persistence and dreamspace resolution.

    Gates on SEED_SAMPLE_CONTENT (#2698) — drives the real Sleeping condition,
    same as test_dreamwalk.py/test_sleep_wake.py.
    """

    def setUp(self):
        ensure_foundational_capabilities()
        ensure_sleeping_condition()
        ensure_dream_room()
        self.template = ConditionTemplate.objects.get(name=SLEEPING_CONDITION_NAME)

    def _sleeping_sheet(self, key: str = "Sleeper") -> CharacterSheet:
        """A sleeping character in their own room, with a real dream reflection."""
        char, sheet, _ = create_character_with_sheet(
            character_key=key,
            primary_persona_name=key,
        )
        room = ObjectDBFactory(db_key=f"{key} Room")
        char.location = room
        char.save()
        self._give_reflection(room)
        apply_condition(target=char, condition=self.template)
        return sheet

    def _give_reflection(self, waking_room) -> None:
        """Attach a real DreamReflection to ``waking_room``.

        Without this, get_dream_space() falls back to the liminal room and
        every sheet placed in a fresh room would resolve to the SAME
        dreamspace regardless of dreamwalk state, masking bugs in
        dreamspace_for().
        """
        dream_profile = RoomProfileFactory(
            objectdb=ObjectDBFactory(db_key=f"Dream of {waking_room.db_key}")
        )
        DreamReflection.objects.create(
            waking_room=RoomProfileFactory(objectdb=waking_room),
            dream_room=dream_profile,
        )

    def _two_sleepers_in_different_rooms(self) -> tuple[CharacterSheet, CharacterSheet]:
        walker = self._sleeping_sheet("Walker")
        host = self._sleeping_sheet("Host")
        return walker, host

    def _dream_room_of(self, room):
        return get_dream_space(room=room)

    def _wake(self, sheet: CharacterSheet) -> None:
        remove_condition(sheet.character, self.template)

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
