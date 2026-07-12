"""Tests for door LockAction/UnlockAction and the can_traverse gate (#1866)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.doors import BreakExitAction, LockAction, PickLockAction, UnlockAction
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.services import transfer_ownership
from world.scenes.factories import PersonaFactory


class LockActionTests(TestCase):
    def _room_owner_and_exit(self):
        room = ObjectDBFactory(db_key="DoorLockRoom", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(
            db_key="DoorLockDest", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="door_lock_account")
        actor = CharacterFactory(db_key="DoorLockAlice", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])
        from evennia_extensions.models import RoomProfile

        room_profile = RoomProfile.objects.filter(objectdb=room).first()
        if room_profile is None:
            room_profile = RoomProfile.objects.create(objectdb=room)
        transfer_ownership(room_profile=room_profile, to_persona=persona)
        exit_obj = ObjectDBFactory(db_key="north", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.save()
        return actor, exit_obj

    def test_owner_can_lock_exit(self):
        actor, exit_obj = self._room_owner_and_exit()
        result = LockAction().run(actor=actor, exit=exit_obj)
        assert result.success
        assert exit_obj.db.locked is True

    def test_non_owner_cannot_lock_exit(self):
        room = ObjectDBFactory(db_key="DoorLockRoom2", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(
            db_key="DoorLockDest2", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="door_lock_account_2")
        actor = CharacterFactory(db_key="DoorLockBob", location=room)
        actor.db_account = account
        actor.save()
        CharacterSheetFactory(character=actor)
        exit_obj = ObjectDBFactory(db_key="south", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.save()

        result = LockAction().run(actor=actor, exit=exit_obj)
        assert not result.success


class UnlockActionTests(TestCase):
    def test_owner_can_unlock_exit(self):
        actor, exit_obj = LockActionTests()._room_owner_and_exit()
        exit_obj.db.locked = True
        result = UnlockAction().run(actor=actor, exit=exit_obj)
        assert result.success
        assert exit_obj.db.locked is False


class PickLockActionTests(TestCase):
    """Tests for PickLockAction (#2176) — quiet, check-gated lockpicking."""

    def _actor_and_locked_exit(self):
        room = ObjectDBFactory(db_key="PickLockRoom", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(
            db_key="PickLockDest", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="pick_lock_account")
        actor = CharacterFactory(db_key="PickLockAlice", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])
        exit_obj = ObjectDBFactory(db_key="north", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.db.locked = True
        exit_obj.save()
        return actor, exit_obj, room

    def test_pick_lock_success_unlocks_exit(self):
        from world.checks.test_helpers import force_check_outcome
        from world.seeds.checks import seed_check_resolution_tables
        from world.seeds.investigation_checks import ensure_lockpicking_check
        from world.traits.models import CheckOutcome

        seed_check_resolution_tables()
        ensure_lockpicking_check()
        actor, exit_obj, _room = self._actor_and_locked_exit()

        success_outcome = CheckOutcome.objects.filter(success_level__gt=0).first()
        with force_check_outcome(success_outcome):
            result = PickLockAction().run(actor=actor, exit=exit_obj)

        assert result.success
        assert exit_obj.db.locked is False

    def test_pick_lock_failure_keeps_exit_locked(self):
        from world.checks.test_helpers import force_check_outcome
        from world.seeds.checks import seed_check_resolution_tables
        from world.seeds.investigation_checks import ensure_lockpicking_check
        from world.traits.models import CheckOutcome

        seed_check_resolution_tables()
        ensure_lockpicking_check()
        actor, exit_obj, _room = self._actor_and_locked_exit()

        fail_outcome = CheckOutcome.objects.filter(success_level=0).first()
        with force_check_outcome(fail_outcome):
            result = PickLockAction().run(actor=actor, exit=exit_obj)

        assert not result.success
        assert exit_obj.db.locked is True

    def test_pick_lock_on_unlocked_exit_fails(self):
        actor, exit_obj, _room = self._actor_and_locked_exit()
        exit_obj.db.locked = False
        result = PickLockAction().run(actor=actor, exit=exit_obj)
        assert not result.success

    def test_pick_lock_creates_concealed_deed(self):
        from world.checks.test_helpers import force_check_outcome
        from world.seeds.checks import seed_check_resolution_tables
        from world.seeds.investigation_checks import ensure_lockpicking_check
        from world.societies.models import LegendEntry
        from world.traits.models import CheckOutcome

        seed_check_resolution_tables()
        ensure_lockpicking_check()
        actor, exit_obj, _room = self._actor_and_locked_exit()

        success_outcome = CheckOutcome.objects.filter(success_level__gt=0).first()
        with force_check_outcome(success_outcome):
            PickLockAction().run(actor=actor, exit=exit_obj)

        deeds = LegendEntry.objects.filter(persona=actor.sheet_data.active_persona)
        assert deeds.exists()
        deed = deeds.first()
        assert deed.title.startswith("Lockpicking")

    def test_pick_lock_no_check_type_seeded_fails_gracefully(self):
        actor, exit_obj, _room = self._actor_and_locked_exit()
        result = PickLockAction().run(actor=actor, exit=exit_obj)
        assert not result.success
        assert "available" in result.message.lower()


class BreakExitActionTests(TestCase):
    """Tests for BreakExitAction (#2176) — loud, always-succeeds lock breaking."""

    def _actor_and_locked_exit(self):
        room = ObjectDBFactory(db_key="BreakExitRoom", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(
            db_key="BreakExitDest", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="break_exit_account")
        actor = CharacterFactory(db_key="BreakExitBob", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])
        exit_obj = ObjectDBFactory(db_key="east", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.db.locked = True
        exit_obj.save()
        return actor, exit_obj, room

    def test_break_exit_unlocks_exit(self):
        actor, exit_obj, _room = self._actor_and_locked_exit()
        result = BreakExitAction().run(actor=actor, exit=exit_obj)
        assert result.success
        assert exit_obj.db.locked is False

    def test_break_exit_on_unlocked_exit_fails(self):
        actor, exit_obj, _room = self._actor_and_locked_exit()
        exit_obj.db.locked = False
        result = BreakExitAction().run(actor=actor, exit=exit_obj)
        assert not result.success

    def test_break_exit_creates_non_concealed_deed(self):
        from world.societies.models import LegendEntry

        actor, exit_obj, _room = self._actor_and_locked_exit()
        BreakExitAction().run(actor=actor, exit=exit_obj)

        deeds = LegendEntry.objects.filter(persona=actor.sheet_data.active_persona)
        assert deeds.exists()
        deed = deeds.first()
        assert deed.title.startswith("Break-in")

    def test_break_exit_damages_building_condition(self):
        from evennia_extensions.models import RoomProfile
        from world.areas.factories import AreaFactory
        from world.buildings.constants import ConditionTier
        from world.buildings.factories import BuildingFactory

        actor, exit_obj, room = self._actor_and_locked_exit()
        area = AreaFactory(level=10)
        profile = RoomProfile.objects.filter(objectdb=room).first()
        if profile is None:
            profile = RoomProfile.objects.create(objectdb=room, area=area)
        else:
            profile.area = area
            profile.save(update_fields=["area"])
        building = BuildingFactory(area=area, condition_tier=ConditionTier.EXCELLENT)

        BreakExitAction().run(actor=actor, exit=exit_obj)
        building.refresh_from_db()
        assert building.condition_tier == ConditionTier.GOOD

    def test_break_exit_condition_floors_at_decayed(self):
        from evennia_extensions.models import RoomProfile
        from world.areas.factories import AreaFactory
        from world.buildings.constants import ConditionTier
        from world.buildings.factories import BuildingFactory

        actor, exit_obj, room = self._actor_and_locked_exit()
        area = AreaFactory(level=10)
        profile = RoomProfile.objects.filter(objectdb=room).first()
        if profile is None:
            profile = RoomProfile.objects.create(objectdb=room, area=area)
        else:
            profile.area = area
            profile.save(update_fields=["area"])
        building = BuildingFactory(area=area, condition_tier=ConditionTier.DECAYED)

        BreakExitAction().run(actor=actor, exit=exit_obj)
        building.refresh_from_db()
        assert building.condition_tier == ConditionTier.DECAYED

    def test_break_exit_no_building_succeeds_without_damage(self):
        actor, exit_obj, _room = self._actor_and_locked_exit()
        result = BreakExitAction().run(actor=actor, exit=exit_obj)
        assert result.success


class ExitStateBarsGateTests(TestCase):
    def _owner_actor_room_and_exit(self):
        room = ObjectDBFactory(db_key="BarsGateRoom", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(
            db_key="BarsGateDest", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="bars_gate_account")
        actor = CharacterFactory(db_key="BarsGateAlice", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])
        from evennia_extensions.models import RoomProfile

        room_profile = RoomProfile.objects.filter(objectdb=room).first()
        if room_profile is None:
            room_profile = RoomProfile.objects.create(objectdb=room)
        transfer_ownership(room_profile=room_profile, to_persona=persona)
        exit_obj = ObjectDBFactory(db_key="west", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.save()
        return actor, exit_obj, persona

    def _intruder(self, room):
        account = AccountFactory(username="bars_gate_intruder")
        intruder = CharacterFactory(db_key="BarsGateMallory", location=room)
        intruder.db_account = account
        intruder.save()
        sheet = CharacterSheetFactory(character=intruder)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])
        return intruder

    def test_barred_unlocked_exit_blocks_non_owner(self):
        from evennia_extensions.models import ExitProfile
        from flows.object_states.exit_state import ExitState
        from flows.scene_data_manager import SceneDataManager
        from world.room_features.models import ExitBarsDetails

        actor, exit_obj, _persona = self._owner_actor_room_and_exit()
        exit_profile = ExitProfile.get_or_create_for_exit(exit_obj)
        ExitBarsDetails.objects.create(exit_profile=exit_profile, level=1)
        intruder = self._intruder(actor.location)

        sdm = SceneDataManager()
        exit_state: ExitState = sdm.initialize_state_for_object(exit_obj)
        intruder_state = sdm.initialize_state_for_object(intruder)
        assert exit_obj.db.locked is not True
        assert exit_state.can_traverse(intruder_state) is False

    def test_barred_exit_allows_owner(self):
        from evennia_extensions.models import ExitProfile
        from flows.object_states.exit_state import ExitState
        from flows.scene_data_manager import SceneDataManager
        from world.room_features.models import ExitBarsDetails

        actor, exit_obj, _persona = self._owner_actor_room_and_exit()
        exit_profile = ExitProfile.get_or_create_for_exit(exit_obj)
        ExitBarsDetails.objects.create(exit_profile=exit_profile, level=1)

        sdm = SceneDataManager()
        exit_state: ExitState = sdm.initialize_state_for_object(exit_obj)
        actor_state = sdm.initialize_state_for_object(actor)
        assert exit_state.can_traverse(actor_state) is True

    def test_no_bars_unaffected(self):
        from flows.object_states.exit_state import ExitState
        from flows.scene_data_manager import SceneDataManager

        actor, exit_obj, _persona = self._owner_actor_room_and_exit()
        intruder = self._intruder(actor.location)
        sdm = SceneDataManager()
        exit_state: ExitState = sdm.initialize_state_for_object(exit_obj)
        intruder_state = sdm.initialize_state_for_object(intruder)
        assert exit_state.can_traverse(intruder_state) is True


class BreakExitActionBarsTests(TestCase):
    def _actor_and_barred_unlocked_exit(self):
        from evennia_extensions.models import ExitProfile
        from world.room_features.models import ExitBarsDetails

        room = ObjectDBFactory(db_key="BreakBarsRoom", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(
            db_key="BreakBarsDest", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="break_bars_account")
        actor = CharacterFactory(db_key="BreakBarsDave", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)
        persona = PersonaFactory(character_sheet=sheet)
        sheet.active_persona = persona
        sheet.save(update_fields=["active_persona"])
        exit_obj = ObjectDBFactory(db_key="bars_exit", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.save()
        exit_profile = ExitProfile.get_or_create_for_exit(exit_obj)
        bars = ExitBarsDetails.objects.create(exit_profile=exit_profile, level=2)
        return actor, exit_obj, bars

    def test_break_barred_unlocked_exit_succeeds_and_drops_level(self):
        actor, exit_obj, bars = self._actor_and_barred_unlocked_exit()
        assert exit_obj.db.locked is not True
        result = BreakExitAction().run(actor=actor, exit=exit_obj)
        assert result.success
        bars.refresh_from_db()
        assert bars.level == 1

    def test_break_barred_exit_at_level_1_dissolves_bars(self):
        actor, exit_obj, bars = self._actor_and_barred_unlocked_exit()
        bars.level = 1
        bars.save(update_fields=["level"])
        result = BreakExitAction().run(actor=actor, exit=exit_obj)
        assert result.success
        bars.refresh_from_db()
        assert bars.dissolved_at is not None

    def test_break_locked_and_barred_clears_both(self):
        actor, exit_obj, bars = self._actor_and_barred_unlocked_exit()
        exit_obj.db.locked = True
        result = BreakExitAction().run(actor=actor, exit=exit_obj)
        assert result.success
        assert exit_obj.db.locked is False
        bars.refresh_from_db()
        assert bars.level == 1
