"""Journey test: the GM story-room lifecycle end-to-end (#2450, epic #2436 slice 3).

Exercises the full story-builder action family at the ``action.run()`` layer
(no HTTP): a GM stands up a story area, digs and links two rooms, grants a
player access, the player joins and walks the exit network, the GM spins up
and closes a temp scene room, and staff promotes the area to AUTHORED —
proving the promoted area stops counting against the GM's ``create_story_area``
cap (mirrors ``world.gm.test_story_services.CreateStoryAreaTests
.test_promoted_area_stops_counting_against_cap``, but end-to-end through the
action layer). This is the one test that proves all thirteen story-builder
actions (#2450 tasks 6-7) actually compose, not just each action's own unit
assertions (``actions/tests/test_story_builder_actions.py``).
"""

from __future__ import annotations

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.definitions.story_builder import (
    CloseSceneRoomAction,
    CreateStoryAreaAction,
    GrantStoryRoomAccessAction,
    JoinStoryRoomAction,
    LeaveStoryRoomAction,
    SpinUpSceneRoomAction,
    StoryDigRoomAction,
    StoryLinkRoomsAction,
)
from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from evennia_extensions.models import RoomProfile
from world.areas.grid_services import promote_to_authored
from world.areas.models import Area
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.gm.models import GMProfile
from world.instances.models import InstancedRoom
from world.roster.factories import RosterEntryFactory, RosterTenureFactory

_EXIT_TYPECLASS = "typeclasses.exits.Exit"


def _gm_actor(db_key: str) -> tuple[ObjectDB, GMProfile]:
    """A Character whose account is a non-staff, STARTING-level GM.

    Mirrors ``actions/tests/test_story_builder_actions.py``'s ``_gm_actor`` —
    ``MinimumGMLevelPrerequisite`` resolves the GM account via
    ``actor.active_account`` -> ``sheet_data.roster_entry.current_tenure
    .player_data.account``, which needs a real tenure, not a bare
    ``char.db_account``.
    """
    char = CharacterFactory(db_key=db_key)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    profile = GMProfileFactory(account=account)
    return char, profile


class StoryRoomJourneyTests(TestCase):
    """create_story_area -> story_dig_room x2 -> story_link_rooms ->
    grant/join/leave -> spin_up/grant/join/close -> staff promote_to_authored,
    asserting the cap is freed."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def setUp(self) -> None:
        self.gm_actor, self.gm_profile = _gm_actor("StoryJourneyGM")

        self.origin_room = RoomProfileFactory().objectdb
        self.player = CharacterFactory(db_key="StoryJourneyPlayer", home=self.origin_room)
        CharacterSheetFactory(character=self.player)
        self.player.move_to(self.origin_room, quiet=True)

    def test_full_story_room_journey(self) -> None:
        # 1. Create a story area.
        create_result = CreateStoryAreaAction().run(self.gm_actor, name="Journey Crypt")
        assert create_result.success, create_result.message
        area = Area.objects.get(name="Journey Crypt")

        # 2. Dig two rooms into it.
        dig_a = StoryDigRoomAction().run(self.gm_actor, area_id=area.pk, name="Antechamber")
        assert dig_a.success, dig_a.message
        dig_b = StoryDigRoomAction().run(self.gm_actor, area_id=area.pk, name="Inner Sanctum")
        assert dig_b.success, dig_b.message
        room_a = RoomProfile.objects.get(area=area, objectdb__db_key="Antechamber")
        room_b = RoomProfile.objects.get(area=area, objectdb__db_key="Inner Sanctum")

        # 3. Link them with a named exit pair.
        link_result = StoryLinkRoomsAction().run(
            self.gm_actor,
            room_a_id=room_a.objectdb_id,
            room_b_id=room_b.objectdb_id,
            name="Deeper In",
            reverse_name="Back Out",
        )
        assert link_result.success, link_result.message
        forward_exit = ObjectDB.objects.get(
            db_typeclass_path=_EXIT_TYPECLASS,
            db_location=room_a.objectdb,
            db_destination=room_b.objectdb,
        )
        backward_exit = ObjectDB.objects.get(
            db_typeclass_path=_EXIT_TYPECLASS,
            db_location=room_b.objectdb,
            db_destination=room_a.objectdb,
        )

        # 4. Grant the player access to room A.
        grant_result = GrantStoryRoomAccessAction().run(
            self.gm_actor, room_id=room_a.objectdb_id, character_name=self.player.db_key
        )
        assert grant_result.success, grant_result.message

        # 5. The player joins room A.
        join_result = JoinStoryRoomAction().run(self.player, room_id=room_a.objectdb_id)
        assert join_result.success, join_result.message
        assert self.player.location == room_a.objectdb

        # 6. They walk the exit network to room B and back — plain move_to via
        # the exit's destination, proving story rooms carry ordinary exit
        # connectivity (not the grant-gated join move).
        assert self.player.move_to(forward_exit.db_destination, quiet=True)
        assert self.player.location == room_b.objectdb
        assert self.player.move_to(backward_exit.db_destination, quiet=True)
        assert self.player.location == room_a.objectdb

        # 7. They leave — returned to the origin captured at join time.
        leave_result = LeaveStoryRoomAction().run(self.player)
        assert leave_result.success, leave_result.message
        assert self.player.location == self.origin_room

        # 8. The GM spins up a temp scene room.
        spin_result = SpinUpSceneRoomAction().run(self.gm_actor, name="Ambush Site")
        assert spin_result.success, spin_result.message
        instance = InstancedRoom.objects.get(gm_owner=self.gm_profile, room__db_key="Ambush Site")

        # 9. Grant + join the temp room.
        grant_temp = GrantStoryRoomAccessAction().run(
            self.gm_actor, room_id=instance.room_id, character_name=self.player.db_key
        )
        assert grant_temp.success, grant_temp.message
        join_temp = JoinStoryRoomAction().run(self.player, room_id=instance.room_id)
        assert join_temp.success, join_temp.message
        assert self.player.location == instance.room

        # 10. The GM closes it — the player is returned.
        close_result = CloseSceneRoomAction().run(self.gm_actor, room_id=instance.room_id)
        assert close_result.success, close_result.message
        assert self.player.location == self.origin_room

        # 11. Staff promotes the area (plain slug), then each room
        # (<area-slug>/<room-slug> keys).
        promote_to_authored(area=area, key="story-promo-test")
        promote_to_authored(room_profile=room_a, key="story-promo-test/antechamber")
        promote_to_authored(room_profile=room_b, key="story-promo-test/inner-sanctum")

        # 12. The promoted area no longer counts against the GM's
        # create_story_area cap (STARTING allows exactly 1 live story area).
        second_area_result = CreateStoryAreaAction().run(self.gm_actor, name="Second Crypt")
        assert second_area_result.success, second_area_result.message
        assert Area.objects.filter(name="Second Crypt").exists()
