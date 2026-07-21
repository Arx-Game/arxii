"""Tests for the ghost-tutor summoning service (#2460)."""

from unittest.mock import MagicMock

from django.test import TestCase
import pytest

from world.magic.exceptions import (
    GhostTutelageAlreadyExistsError,
    NotTraditionMemberError,
)
from world.magic.models import GhostTutelage
from world.magic.services.ghost_tutor import summon_ghost_tutor


class SummonGhostTutorTests(TestCase):
    """Tests for summon_ghost_tutor service function."""

    @classmethod
    def setUpTestData(cls):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterTraditionFactory,
            TraditionFactory,
        )

        cls.sheet = CharacterSheetFactory()
        cls.tradition = TraditionFactory()
        CharacterTraditionFactory(
            character=cls.sheet,
            tradition=cls.tradition,
            left_at=None,
        )
        cls.ritual = MagicMock()  # The ritual instance is opaque to the service

    def test_creates_tutelage_for_member(self):
        """Summoning creates a GhostTutelage for an active tradition member."""
        result = summon_ghost_tutor(
            character_sheet=self.sheet,
            ritual=self.ritual,
            tradition=self.tradition,
        )
        assert result["created"] is True
        assert (
            GhostTutelage.objects.filter(
                character_sheet=self.sheet, tradition=self.tradition
            ).count()
            == 1
        )

    def test_not_member_raises(self):
        """Summoning for a tradition the character isn't a member of raises."""
        from world.magic.factories import TraditionFactory

        other_tradition = TraditionFactory()
        with pytest.raises(NotTraditionMemberError):
            summon_ghost_tutor(
                character_sheet=self.sheet,
                ritual=self.ritual,
                tradition=other_tradition,
            )

    def test_already_summoned_raises(self):
        """Re-summoning raises (so components are refunded via rollback)."""
        summon_ghost_tutor(
            character_sheet=self.sheet,
            ritual=self.ritual,
            tradition=self.tradition,
        )
        with pytest.raises(GhostTutelageAlreadyExistsError):
            summon_ghost_tutor(
                character_sheet=self.sheet,
                ritual=self.ritual,
                tradition=self.tradition,
            )

    def test_left_tradition_raises(self):
        """A character who left the tradition can't summon its tutor."""
        from world.magic.models.gifts import CharacterTradition

        # Mark the membership as left
        CharacterTradition.objects.filter(character=self.sheet, tradition=self.tradition).update(
            left_at="2026-01-01T00:00:00Z"
        )

        with pytest.raises(NotTraditionMemberError):
            summon_ghost_tutor(
                character_sheet=self.sheet,
                ritual=self.ritual,
                tradition=self.tradition,
            )
