"""Tests for @target parsing."""

from __future__ import annotations

from django.test import TestCase

from commands.parsing import parse_targets_from_text
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory


class TestParseTargetsFromText(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.bob = CharacterFactory(db_key="Bob", location=self.room)
        self.carol = CharacterFactory(db_key="Carol", location=self.room)

    def test_single_target(self) -> None:
        remaining, targets = parse_targets_from_text("@Bob waves hello", self.room)
        assert remaining == "waves hello"
        assert len(targets) == 1
        assert targets[0].pk == self.bob.pk

    def test_multiple_targets(self) -> None:
        remaining, targets = parse_targets_from_text("@Bob,@Carol waves", self.room)
        assert remaining == "waves"
        assert len(targets) == 2
        target_pks = {t.pk for t in targets}
        assert self.bob.pk in target_pks
        assert self.carol.pk in target_pks

    def test_no_target_prefix(self) -> None:
        remaining, targets = parse_targets_from_text("waves hello", self.room)
        assert remaining == "waves hello"
        assert targets == []

    def test_target_not_in_room(self) -> None:
        remaining, targets = parse_targets_from_text("@Nobody waves", self.room)
        assert remaining == "waves"
        assert targets == []

    def test_case_insensitive(self) -> None:
        remaining, targets = parse_targets_from_text("@bob waves", self.room)
        assert remaining == "waves"
        assert len(targets) == 1
        assert targets[0].pk == self.bob.pk

    def test_mixed_valid_and_invalid_targets(self) -> None:
        remaining, targets = parse_targets_from_text("@Bob,@Nobody waves", self.room)
        assert remaining == "waves"
        assert len(targets) == 1
        assert targets[0].pk == self.bob.pk

    def test_at_sign_only_no_space(self) -> None:
        """@name with no remaining text returns original text."""
        remaining, targets = parse_targets_from_text("@Bob", self.room)
        # No space after target means no match on the regex — returns original
        assert remaining == "@Bob"
        assert targets == []
