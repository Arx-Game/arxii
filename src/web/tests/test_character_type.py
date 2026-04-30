"""Tests for character_type derivation from typeclass path."""

from django.test import TestCase

from evennia_extensions.factories import (
    CharacterFactory,
    GMCharacterFactory,
    StaffCharacterFactory,
)
from web.api.character_type import derive_character_type


class DeriveCharacterTypeTests(TestCase):
    """Map typeclass paths to high-level character_type strings."""

    def test_default_character_is_pc(self) -> None:
        char = CharacterFactory()
        assert derive_character_type(char) == "PC"

    def test_gm_character_is_gm(self) -> None:
        char = GMCharacterFactory()
        assert derive_character_type(char) == "GM"

    def test_staff_character_is_staff(self) -> None:
        char = StaffCharacterFactory()
        assert derive_character_type(char) == "STAFF"
