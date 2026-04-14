"""
Tests for roster selector functions.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.roster.selectors import get_account_for_character


class GetAccountForCharacterTest(TestCase):
    """Tests for get_account_for_character selector."""

    def test_active_tenure_returns_account(self) -> None:
        """Character with an active tenure returns the associated account."""
        player_data = PlayerDataFactory()
        character = CharacterFactory()
        entry = RosterEntryFactory(character_sheet__character=character)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)

        result = get_account_for_character(character)

        assert result is not None
        assert result.pk == player_data.account.pk

    def test_ended_tenure_returns_none(self) -> None:
        """Character whose tenure has ended returns None."""
        from django.utils import timezone

        player_data = PlayerDataFactory()
        character = CharacterFactory()
        entry = RosterEntryFactory(character_sheet__character=character)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=player_data,
            end_date=timezone.now(),
        )

        result = get_account_for_character(character)

        assert result is None

    def test_no_roster_entry_returns_none(self) -> None:
        """Character with no roster entry at all returns None."""
        character = CharacterFactory()

        result = get_account_for_character(character)

        assert result is None
