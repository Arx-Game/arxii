"""Tests for GM and Staff character typeclasses."""

from django.test import TestCase
from evennia import create_object

from typeclasses.characters import Character
from typeclasses.gm_characters import GMCharacter, StaffCharacter


class GMCharacterClassTest(TestCase):
    """Test GMCharacter typeclass structure."""

    def test_extends_character(self) -> None:
        assert issubclass(GMCharacter, Character)

    def test_has_targeting_rejection(self) -> None:
        assert GMCharacter.TARGETING_REJECTION
        assert "story" in GMCharacter.TARGETING_REJECTION.lower()

    def test_has_rejection_method(self) -> None:
        assert hasattr(GMCharacter, "get_targeting_rejection_message")


class StaffCharacterClassTest(TestCase):
    """Test StaffCharacter typeclass structure."""

    def test_extends_character(self) -> None:
        assert issubclass(StaffCharacter, Character)

    def test_not_subclass_of_gm(self) -> None:
        """StaffCharacter is not a subclass of GMCharacter."""
        assert not issubclass(StaffCharacter, GMCharacter)

    def test_has_targeting_rejection(self) -> None:
        assert StaffCharacter.TARGETING_REJECTION
        assert "narrative" in StaffCharacter.TARGETING_REJECTION.lower()

    def test_has_rejection_method(self) -> None:
        assert hasattr(StaffCharacter, "get_targeting_rejection_message")


class GMCharacterCreationTest(TestCase):
    """Test that at_object_creation runs and sets locks."""

    def test_locks_added_on_creation(self) -> None:
        gm = create_object(
            "typeclasses.gm_characters.GMCharacter",
            key="TestGM",
        )
        try:
            lockstrings = gm.locks.all()
            assert any("combat_target:false()" in s for s in lockstrings)
            assert any("give_to:false()" in s for s in lockstrings)
        finally:
            gm.delete()

    def test_combat_target_lock_denies(self) -> None:
        gm = create_object(
            "typeclasses.gm_characters.GMCharacter",
            key="TestGMDeny",
        )
        try:
            assert not gm.access(gm, "combat_target")
            assert not gm.access(gm, "give_to")
        finally:
            gm.delete()

    def test_rejection_message_returns_string(self) -> None:
        gm = create_object(
            "typeclasses.gm_characters.GMCharacter",
            key="TestGMMsg",
        )
        try:
            msg = gm.get_targeting_rejection_message()
            assert isinstance(msg, str)
            assert "story" in msg.lower()
        finally:
            gm.delete()


class StaffCharacterCreationTest(TestCase):
    """Test that at_object_creation runs and sets locks for StaffCharacter."""

    def test_staff_locks_added_on_creation(self) -> None:
        staff = create_object(
            "typeclasses.gm_characters.StaffCharacter",
            key="TestStaff",
        )
        try:
            lockstrings = staff.locks.all()
            assert any("combat_target:false()" in s for s in lockstrings)
            assert any("give_to:false()" in s for s in lockstrings)
        finally:
            staff.delete()

    def test_combat_target_lock_denies(self) -> None:
        staff = create_object(
            "typeclasses.gm_characters.StaffCharacter",
            key="TestStaffDeny",
        )
        try:
            assert not staff.access(staff, "combat_target")
            assert not staff.access(staff, "give_to")
        finally:
            staff.delete()

    def test_rejection_message_returns_string(self) -> None:
        staff = create_object(
            "typeclasses.gm_characters.StaffCharacter",
            key="TestStaffMsg",
        )
        try:
            msg = staff.get_targeting_rejection_message()
            assert isinstance(msg, str)
            assert "narrative" in msg.lower()
        finally:
            staff.delete()
