"""Tests for GM and Staff character typeclasses."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
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


class GMCharacterLockTest(TestCase):
    """Test GMCharacter lock behavior using ObjectDBFactory."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gm = ObjectDBFactory(
            db_key="storyteller",
            db_typeclass_path="typeclasses.gm_characters.GMCharacter",
        )

    def test_combat_target_lock_denies(self) -> None:
        assert not self.gm.access(self.gm, "combat_target")

    def test_give_to_lock_denies(self) -> None:
        assert not self.gm.access(self.gm, "give_to")

    def test_rejection_message_returns_string(self) -> None:
        msg = self.gm.get_targeting_rejection_message()
        assert isinstance(msg, str)
        assert "story" in msg.lower()


class StaffCharacterLockTest(TestCase):
    """Test StaffCharacter lock behavior using ObjectDBFactory."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = ObjectDBFactory(
            db_key="admin",
            db_typeclass_path="typeclasses.gm_characters.StaffCharacter",
        )

    def test_combat_target_lock_denies(self) -> None:
        assert not self.staff.access(self.staff, "combat_target")

    def test_give_to_lock_denies(self) -> None:
        assert not self.staff.access(self.staff, "give_to")

    def test_rejection_message_returns_string(self) -> None:
        msg = self.staff.get_targeting_rejection_message()
        assert isinstance(msg, str)
        assert "narrative" in msg.lower()
