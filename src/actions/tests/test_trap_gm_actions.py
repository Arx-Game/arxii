"""Tests for the GM trap management actions (#3002).

DbHolder trap: every Evennia ObjectDB fixture (room, character) is built in
setUp, never setUpTestData.
"""

from django.test import TestCase
from evennia import create_object

from actions.definitions.traps import (
    ArmTrapAction,
    GmDisarmTrapAction,
    ListRoomTrapsAction,
)
from evennia_extensions.factories import CharacterFactory
from evennia_extensions.models import RoomProfile
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.room_features.factories import TrapFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.interaction_services import invalidate_active_scene_cache


class GMTrapActionTestBase(TestCase):
    """A scene-GM actor standing in a room that holds one armed trap."""

    def setUp(self) -> None:
        super().setUp()
        self.room = create_object("typeclasses.rooms.Room", key="Trapped Hall", nohome=True)
        self.room_profile, _ = RoomProfile.objects.get_or_create(objectdb=self.room)
        self.trap = TrapFactory(room_profile=self.room_profile, name="Spike Pit")

    def _gm_in_scene(self, level: str = GMLevel.JUNIOR, *, db_key: str = "gm") -> object:
        """A Character with GM trust at ``level`` who runs the active scene in self.room."""
        character = CharacterFactory(db_key=db_key, location=self.room)
        CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet__character=character)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        account = tenure.player_data.account
        GMProfileFactory(account=account, level=level)
        scene = SceneFactory(location=self.room)
        SceneParticipationFactory(scene=scene, account=account, is_gm=True)
        invalidate_active_scene_cache(self.room)
        return character

    def _gm_without_scene(self, level: str = GMLevel.JUNIOR) -> object:
        """GM trust at ``level`` but not running any scene here."""
        character = CharacterFactory(db_key="bystander-gm", location=self.room)
        CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet__character=character)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        GMProfileFactory(account=tenure.player_data.account, level=level)
        invalidate_active_scene_cache(self.room)
        return character


class ListRoomTrapsActionTest(GMTrapActionTestBase):
    def test_scene_gm_sees_the_trap(self) -> None:
        actor = self._gm_in_scene()

        result = ListRoomTrapsAction().run(actor)

        assert result.success is True
        rows = result.data["traps"]
        assert [row["id"] for row in rows] == [self.trap.pk]
        assert rows[0]["name"] == "Spike Pit"
        assert rows[0]["is_armed"] is True

    def test_trap_in_another_room_is_not_listed(self) -> None:
        actor = self._gm_in_scene()
        other_room = create_object("typeclasses.rooms.Room", key="Elsewhere", nohome=True)
        other_profile, _ = RoomProfile.objects.get_or_create(objectdb=other_room)
        TrapFactory(room_profile=other_profile, name="Far Snare")

        result = ListRoomTrapsAction().run(actor)

        assert [row["name"] for row in result.data["traps"]] == ["Spike Pit"]

    def test_non_scene_gm_sees_no_traps_they_did_not_place(self) -> None:
        """Widened by #3002 review finding 1: a GM with no active scene here is no
        longer refused outright - they see a FILTERED list. ``self.trap`` has a null
        ``created_by_sheet`` (admin-authored), so it is absent for this actor."""
        actor = self._gm_without_scene()

        result = ListRoomTrapsAction().run(actor)

        assert result.success is True
        assert result.data["traps"] == []

    def test_scene_gm_manages_a_trap_it_did_not_place(self) -> None:
        """The widened gate must not narrow the mid-scene case: the scene's GM still
        sees and can manage a trap someone else placed."""
        actor = self._gm_in_scene()
        other_sheet = CharacterSheetFactory()
        others_trap = TrapFactory(
            room_profile=self.room_profile, name="Not Mine", created_by_sheet=other_sheet
        )

        result = ListRoomTrapsAction().run(actor)

        listed_ids = {row["id"] for row in result.data["traps"]}
        assert others_trap.pk in listed_ids

        disarm_result = GmDisarmTrapAction().run(actor, trap_id=others_trap.pk)

        assert disarm_result.success is True
        others_trap.refresh_from_db()
        assert others_trap.is_armed is False


class ArmTrapActionTest(GMTrapActionTestBase):
    def test_rearms_a_disarmed_trap(self) -> None:
        actor = self._gm_in_scene()
        self.trap.is_armed = False
        self.trap.save(update_fields=["is_armed"])

        result = ArmTrapAction().run(actor, trap_id=self.trap.pk)

        assert result.success is True
        self.trap.refresh_from_db()
        assert self.trap.is_armed is True

    def test_sub_junior_gm_is_refused_and_trap_is_untouched(self) -> None:
        actor = self._gm_in_scene(GMLevel.STARTING, db_key="starting-gm")
        self.trap.is_armed = False
        self.trap.save(update_fields=["is_armed"])

        result = ArmTrapAction().run(actor, trap_id=self.trap.pk)

        assert result.success is False
        self.trap.refresh_from_db()
        assert self.trap.is_armed is False

    def test_trap_in_another_room_is_refused(self) -> None:
        actor = self._gm_in_scene()
        other_room = create_object("typeclasses.rooms.Room", key="Elsewhere", nohome=True)
        other_profile, _ = RoomProfile.objects.get_or_create(objectdb=other_room)
        far_trap = TrapFactory(room_profile=other_profile, name="Far Snare", is_armed=False)

        result = ArmTrapAction().run(actor, trap_id=far_trap.pk)

        assert result.success is False
        far_trap.refresh_from_db()
        assert far_trap.is_armed is False

    def test_missing_trap_id_fails(self) -> None:
        actor = self._gm_in_scene()

        result = ArmTrapAction().run(actor)

        assert result.success is False

    def test_refuses_to_rearm_a_spent_zone_hazard(self) -> None:
        """#3002 review finding 2: a zone hazard whose duration already ticked to 0
        must not be re-armable - tick_zone_hazards decrements duration_rounds with no
        floor, so re-arming it would drive it negative and crash Postgres's
        PositiveIntegerField check constraint."""
        actor = self._gm_in_scene()
        hazard = TrapFactory(
            room_profile=self.room_profile,
            name="Guttering Ward",
            duration_rounds=0,
            is_armed=False,
            created_by_sheet=actor.character_sheet,
        )

        result = ArmTrapAction().run(actor, trap_id=hazard.pk)

        assert result.success is False
        assert "duration" in result.message.lower()
        hazard.refresh_from_db()
        assert hazard.is_armed is False


class GmDisarmTrapActionTest(GMTrapActionTestBase):
    def test_disarms_without_rolling(self) -> None:
        actor = self._gm_in_scene()

        result = GmDisarmTrapAction().run(actor, trap_id=self.trap.pk)

        assert result.success is True
        self.trap.refresh_from_db()
        assert self.trap.is_armed is False

    def test_non_scene_gm_is_refused_and_trap_stays_armed(self) -> None:
        actor = self._gm_without_scene()

        result = GmDisarmTrapAction().run(actor, trap_id=self.trap.pk)

        assert result.success is False
        self.trap.refresh_from_db()
        assert self.trap.is_armed is True


class PreSceneStagingTest(GMTrapActionTestBase):
    """A JUNIOR GM staging a room ahead of players arriving, no scene active yet.

    #3002 review finding 1: the old scene-only gate dead-ended this documented
    workflow (docs/roadmap/gm-system.md's "Table-running tools" note). The widened
    rule lets this GM manage a trap they placed themselves, while still refusing
    them a trap someone else placed (or an admin-authored one) - preserving the
    anti-metagaming property the scene gate used to provide alone.
    """

    def test_gm_manages_only_the_trap_they_placed(self) -> None:
        actor = self._gm_without_scene()
        own_trap = TrapFactory(
            room_profile=self.room_profile,
            name="Own Snare",
            created_by_sheet=actor.character_sheet,
            is_armed=False,
        )

        list_result = ListRoomTrapsAction().run(actor)
        assert list_result.success is True
        assert {row["id"] for row in list_result.data["traps"]} == {own_trap.pk}

        arm_result = ArmTrapAction().run(actor, trap_id=own_trap.pk)
        assert arm_result.success is True
        own_trap.refresh_from_db()
        assert own_trap.is_armed is True

        disarm_result = GmDisarmTrapAction().run(actor, trap_id=own_trap.pk)
        assert disarm_result.success is True
        own_trap.refresh_from_db()
        assert own_trap.is_armed is False

    def test_gm_cannot_see_or_touch_traps_they_did_not_place(self) -> None:
        actor = self._gm_without_scene()
        other_sheet = CharacterSheetFactory()
        others_trap = TrapFactory(
            room_profile=self.room_profile,
            name="Someone Else's Snare",
            created_by_sheet=other_sheet,
            is_armed=True,
        )
        # self.trap (from setUp) has a null created_by_sheet - admin-authored,
        # is_armed=True by default.

        list_result = ListRoomTrapsAction().run(actor)
        listed_ids = {row["id"] for row in list_result.data["traps"]}
        assert self.trap.pk not in listed_ids
        assert others_trap.pk not in listed_ids

        for trap in (self.trap, others_trap):
            arm_result = ArmTrapAction().run(actor, trap_id=trap.pk)
            assert arm_result.success is False
            disarm_result = GmDisarmTrapAction().run(actor, trap_id=trap.pk)
            assert disarm_result.success is False
            trap.refresh_from_db()
            assert trap.is_armed is True
