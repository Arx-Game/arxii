"""Tests for durable server-side character selection — state 2.5 substrate (#3412).

Selection is NOT presence: these tests cover the `set_selected_entry` service
(own-entry validation, foreign rejection, clearing, SET_NULL survival) and
assert that setting a selection triggers zero lifecycle/session/puppeting
side effects.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.roster.models import RosterTenure
from world.roster.services.selection import SelectionError, set_selected_entry


def _entry_for(player_data):
    """Create a RosterEntry with a current active tenure for player_data —
    i.e. one of the account's "own current entries" per get_available_characters."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(player_data=player_data, roster_entry=entry)
    return entry


class SetSelectedEntryTests(TestCase):
    def setUp(self):
        self.player = PlayerDataFactory()
        self.entry = _entry_for(self.player)

    def test_set_own_entry_ok(self):
        set_selected_entry(self.player, self.entry)
        self.assertEqual(self.player.selected_entry_id, self.entry.pk)
        self.player.refresh_from_db()
        self.assertEqual(self.player.selected_entry_id, self.entry.pk)

    def test_set_foreign_entry_rejected(self):
        other_player = PlayerDataFactory()
        foreign_entry = _entry_for(other_player)
        with self.assertRaises(SelectionError):
            set_selected_entry(self.player, foreign_entry)
        self.assertIsNone(self.player.selected_entry_id)

    def test_set_entry_not_owned_by_anyone_rejected(self):
        # A RosterEntry with no tenure for this player at all.
        unowned = RosterEntryFactory()
        with self.assertRaises(SelectionError):
            set_selected_entry(self.player, unowned)

    def test_clear_ok(self):
        set_selected_entry(self.player, self.entry)
        set_selected_entry(self.player, None)
        self.assertIsNone(self.player.selected_entry_id)
        self.player.refresh_from_db()
        self.assertIsNone(self.player.selected_entry_id)

    def test_clear_always_allowed_even_with_no_prior_selection(self):
        # No prior selection — clearing is a no-op, never rejected.
        set_selected_entry(self.player, None)
        self.assertIsNone(self.player.selected_entry_id)

    def test_set_null_on_entry_deletion(self):
        set_selected_entry(self.player, self.entry)
        self.entry.delete()
        # A Collector-driven SET_NULL bypasses per-instance .save(), so the
        # resident identity-map instance keeps a stale scalar selected_entry_id
        # even after refresh_from_db() — flush it first (sharedmemory-model
        # skill, "stale-cache-traps" case #2).
        PlayerData.flush_instance_cache()
        self.player.refresh_from_db()
        self.assertIsNone(self.player.selected_entry_id)

    def test_selection_triggers_no_lifecycle_side_effects(self):
        """Selecting a character must not create/modify tenures, puppet
        state, or the entry's last_puppeted lifecycle timestamp."""
        tenure_count_before = RosterTenure.objects.count()
        self.assertIsNone(self.entry.last_puppeted)

        set_selected_entry(self.player, self.entry)

        self.assertEqual(RosterTenure.objects.count(), tenure_count_before)
        self.entry.refresh_from_db()
        self.assertIsNone(self.entry.last_puppeted)
        # No session/puppet state exists at all for this player's account —
        # selection required none to succeed.
        self.assertFalse(self.player.account.sessions.all())
