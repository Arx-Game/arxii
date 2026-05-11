"""Tests for can_engage_durance_membership shared prerequisite helper."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.scenes.factories import SceneFactory


def _make_room(key: str = "TestRoom"):
    """Create a Room typeclass instance for use as a scene location."""
    return ObjectDBFactory(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


class EngagementPrerequisiteBranchesTests(TestCase):
    """Cover all branches of can_engage_durance_membership."""

    @classmethod
    def setUpTestData(cls) -> None:
        # DURANCE covenant with two members
        cls.cov_durance = CovenantFactory(name="DuranceCov", covenant_type=CovenantType.DURANCE)
        cls.role_durance = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)

        cls.sheet_a = CharacterSheetFactory()
        cls.sheet_b = CharacterSheetFactory()

        cls.mem_a_durance = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet_a,
            covenant=cls.cov_durance,
            covenant_role=cls.role_durance,
        )
        cls.mem_b_durance = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet_b,
            covenant=cls.cov_durance,
            covenant_role=cls.role_durance,
        )

        # BATTLE covenant with sheet_a as a member
        cls.cov_battle = CovenantFactory(name="BattleCov", covenant_type=CovenantType.BATTLE)
        cls.role_battle = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        cls.mem_a_battle = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet_a,
            covenant=cls.cov_battle,
            covenant_role=cls.role_battle,
        )

    def test_battle_short_circuits_true(self) -> None:
        """Battle membership: helper returns True regardless of co-presence."""
        from world.covenants.handlers import can_engage_durance_membership

        self.assertTrue(can_engage_durance_membership(self.mem_a_battle))

    def test_no_location_returns_false(self) -> None:
        """Character has no location: returns False."""
        from world.covenants.handlers import can_engage_durance_membership

        # CharacterFactory creates character with no location by default (nohome=True)
        # sheet_a's character should have no location at this point in setUpTestData
        char_a = self.sheet_a.character
        # Ensure no location is set
        char_a.db_location = None
        char_a.save(update_fields=["db_location"])

        self.assertFalse(can_engage_durance_membership(self.mem_a_durance))

    def test_no_active_scene_returns_false(self) -> None:
        """Character is in a room but no active scene: returns False."""
        from world.covenants.handlers import can_engage_durance_membership

        room = _make_room("ScenelessRoom")
        char_a = self.sheet_a.character
        char_a.db_location = room
        char_a.save(update_fields=["db_location"])
        # Invalidate the scene cache if any
        if hasattr(room, "_active_scene_cache"):
            del room._active_scene_cache

        # No Scene created at this room → _get_active_scene returns None
        self.assertFalse(can_engage_durance_membership(self.mem_a_durance))

        # Cleanup location so other tests start fresh
        char_a.db_location = None
        char_a.save(update_fields=["db_location"])

    def test_no_co_present_members_returns_false(self) -> None:
        """Character alone in scene (no other covenant members present): returns False."""
        from world.covenants.handlers import can_engage_durance_membership

        room = _make_room("SoloRoom")
        char_a = self.sheet_a.character
        char_a.db_location = room
        char_a.save(update_fields=["db_location"])
        if hasattr(room, "_active_scene_cache"):
            del room._active_scene_cache

        # Active scene at room, but char_b is not in this room
        SceneFactory(location=room, is_active=True)

        self.assertFalse(can_engage_durance_membership(self.mem_a_durance))

        char_a.db_location = None
        char_a.save(update_fields=["db_location"])

    def test_with_co_present_member_returns_true(self) -> None:
        """Two characters in same room with active scene, both in same Durance covenant → True."""
        from world.covenants.handlers import can_engage_durance_membership

        room = _make_room("SharedRoom")
        char_a = self.sheet_a.character
        char_b = self.sheet_b.character
        char_a.db_location = room
        char_b.db_location = room
        char_a.save(update_fields=["db_location"])
        char_b.save(update_fields=["db_location"])
        if hasattr(room, "_active_scene_cache"):
            del room._active_scene_cache

        SceneFactory(location=room, is_active=True)

        self.assertTrue(can_engage_durance_membership(self.mem_a_durance))

        char_a.db_location = None
        char_b.db_location = None
        char_a.save(update_fields=["db_location"])
        char_b.save(update_fields=["db_location"])

    def test_excludes_self_from_co_presence(self) -> None:
        """Helper must NOT count the character themselves as co-present.

        Confirms the exclusion by placing only the target character in the room,
        with no other covenant members — same as the no_co_present case.
        """
        from world.covenants.handlers import can_engage_durance_membership

        room = _make_room("SelfOnlyRoom")
        char_a = self.sheet_a.character
        char_a.db_location = room
        char_a.save(update_fields=["db_location"])
        if hasattr(room, "_active_scene_cache"):
            del room._active_scene_cache

        SceneFactory(location=room, is_active=True)

        # Only char_a is in the room — self must not be counted
        self.assertFalse(can_engage_durance_membership(self.mem_a_durance))

        char_a.db_location = None
        char_a.save(update_fields=["db_location"])
