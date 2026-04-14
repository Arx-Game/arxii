"""Tests for GM and Staff character typeclasses."""

from django.test import TestCase

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


class MechanicalImmunityTest(TestCase):
    """Verify the attribute-based immunity marker."""

    def test_gm_character_is_immune(self) -> None:
        assert GMCharacter.is_mechanically_immune is True

    def test_staff_character_is_immune(self) -> None:
        assert StaffCharacter.is_mechanically_immune is True

    def test_base_character_is_not_immune(self) -> None:
        assert Character.is_mechanically_immune is False

    def test_rejection_message_returns_string(self) -> None:
        gm_msg = GMCharacter.TARGETING_REJECTION
        staff_msg = StaffCharacter.TARGETING_REJECTION
        assert "story" in gm_msg.lower()
        assert "narrative" in staff_msg.lower()
