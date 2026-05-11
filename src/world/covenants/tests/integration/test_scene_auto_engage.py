"""Integration tests for scene-driven auto-engagement subscriptions.

Verifies that ``evaluate_scene_engagement`` is wired into:
- move_object (Task 7.2)
- ensure_scene_for_location (Task 7.3)
- _ensure_scene_participation (Task 7.4)

Note: these tests use ``setUp`` (not ``setUpTestData``) because Evennia
typeclasses (ObjectDB subclasses) are not deepcopy-safe, which Django's
``setUpTestData`` mechanism requires.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.scenes.factories import SceneFactory


def _make_room(key: str = "TestRoom"):
    """Create a Room typeclass instance usable as a scene location."""
    return ObjectDBFactory(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _place_character_in_room(character, room) -> None:
    """Set a character's db_location directly and bust the scene cache."""
    character.db_location = room
    character.save(update_fields=["db_location"])
    if hasattr(room, "_active_scene_cache"):
        del room._active_scene_cache


class MoveObjectAutoEngageTests(TestCase):
    """Task 7.2: moving into a room with a co-present covenant member engages."""

    def test_moving_into_room_with_co_present_member_engages(self) -> None:
        """move_object wires evaluate_scene_engagement so char_a auto-engages on entry."""
        from flows.scene_data_manager import SceneDataManager
        from flows.service_functions.movement import move_object

        cov = CovenantFactory(name="MoveCov", covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        mem_a = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)
        mem_b = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)

        room = _make_room("MoveRoom")
        char_a = mem_a.character_sheet.character
        char_b = mem_b.character_sheet.character

        # char_b is already in the room; active scene is live.
        _place_character_in_room(char_b, room)
        SceneFactory(location=room, is_active=True)

        # char_a starts in a different room.
        start_room = _make_room("StartRoom")
        _place_character_in_room(char_a, start_room)

        self.assertFalse(mem_a.engaged)

        sdm = SceneDataManager()
        obj_state = sdm.initialize_state_for_object(char_a)
        dest_state = sdm.initialize_state_for_object(room)

        move_object(obj_state, dest_state, quiet=True)

        mem_a.refresh_from_db()
        self.assertTrue(mem_a.engaged)


class StartSceneAutoEngageTests(TestCase):
    """Task 7.3: starting a scene at a room engages co-present members."""

    def test_starting_scene_at_room_with_two_covenant_members_engages_both(self) -> None:
        """ensure_scene_for_location calls evaluate_scene_engagement for each occupant."""
        from world.scenes.place_services import ensure_scene_for_location

        cov = CovenantFactory(name="StartSceneCov", covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        mem_a = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)
        mem_b = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)

        room = _make_room("SceneStartRoom")
        char_a = mem_a.character_sheet.character
        char_b = mem_b.character_sheet.character

        # Both members already in the room, no scene yet.
        _place_character_in_room(char_a, room)
        _place_character_in_room(char_b, room)

        self.assertFalse(mem_a.engaged)
        self.assertFalse(mem_b.engaged)

        # Creating the scene should auto-engage both members.
        ensure_scene_for_location(room)

        mem_a.refresh_from_db()
        mem_b.refresh_from_db()
        self.assertTrue(mem_a.engaged)
        self.assertTrue(mem_b.engaged)

    def test_existing_scene_does_not_re_evaluate(self) -> None:
        """ensure_scene_for_location returns early (no evaluate) when a scene pre-exists.

        Confirms the ``created`` guard — if engaged=False and the room already has an active
        scene, a second call to ensure_scene_for_location does NOT flip engaged.
        """
        from world.scenes.place_services import ensure_scene_for_location

        cov = CovenantFactory(name="ExistingSceneCov", covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        mem_a = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)

        room = _make_room("ExistingSceneRoom")
        char_a = mem_a.character_sheet.character
        _place_character_in_room(char_a, room)
        SceneFactory(location=room, is_active=True)  # scene pre-exists

        # Manually keep engaged=False.
        mem_a.engaged = False
        mem_a.save(update_fields=["engaged"])

        # ensure_scene_for_location returns existing scene — no auto-engage.
        scene = ensure_scene_for_location(room)
        self.assertIsNotNone(scene)

        mem_a.refresh_from_db()
        self.assertFalse(mem_a.engaged)


class SceneParticipationAutoEngageTests(TestCase):
    """Task 7.4: joining a scene as a participant evaluates engagement."""

    def test_joining_active_scene_with_co_present_member_engages(self) -> None:
        """_ensure_scene_participation calls evaluate_scene_engagement on the joining character."""
        from world.scenes.interaction_services import _ensure_scene_participation

        cov = CovenantFactory(name="ParticipationCov", covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        mem_a = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)
        mem_b = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)

        room = _make_room("ParticipationRoom")
        char_a = mem_a.character_sheet.character
        char_b = mem_b.character_sheet.character

        # Both characters in the same room, active scene exists.
        _place_character_in_room(char_a, room)
        _place_character_in_room(char_b, room)
        scene = SceneFactory(location=room, is_active=True)

        self.assertFalse(mem_a.engaged)

        # char_a joins the scene via the participation pathway.
        _ensure_scene_participation(scene, char_a)

        mem_a.refresh_from_db()
        self.assertTrue(mem_a.engaged)
