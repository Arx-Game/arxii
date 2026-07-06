"""Tests for player_pending_treasured_signoffs (#1853)."""

from django.test import TestCase

from world.boundaries.factories import TreasuredSubjectFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.stories.constants import StakeSubjectKind
from world.stories.factories import BeatFactory, StakeFactory
from world.stories.services.boundaries import (
    grant_treasured_signoff,
    player_pending_treasured_signoffs,
)


def _sheet_with_player():
    """A CharacterSheet with a live current tenure (roster_entry -> tenure -> player_data)."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    player_data = PlayerDataFactory()
    tenure = RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return sheet, tenure, player_data


class PlayerPendingTreasuredSignoffsTests(TestCase):
    def test_flags_a_staked_treasured_subject_without_signoff(self):
        beat = BeatFactory()
        _sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )

        entries = player_pending_treasured_signoffs(player_data, [beat])

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].beat_id, beat.pk)
        self.assertEqual(entries[0].treasured_subject_ids, (treasured.pk,))

    def test_signed_off_subject_is_excluded(self):
        beat = BeatFactory()
        _sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        grant_treasured_signoff(beat, player_data, treasured)

        entries = player_pending_treasured_signoffs(player_data, [beat])

        self.assertEqual(entries, [])

    def test_unrelated_stake_never_appears(self):
        """A stake matching no treasured subject of this player produces no entry."""
        beat = BeatFactory()
        _sheet, _tenure, player_data = _sheet_with_player()
        StakeFactory(beat=beat, template=None, subject_label="Ordinary wager")

        entries = player_pending_treasured_signoffs(player_data, [beat])

        self.assertEqual(entries, [])

    def test_another_players_treasured_subject_never_appears(self):
        """Player-safe: a different player's treasured subject match is invisible here."""
        beat = BeatFactory()
        _sheet, tenure, _other_player_data = _sheet_with_player()
        TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        querying_player_data = PlayerDataFactory()

        entries = player_pending_treasured_signoffs(querying_player_data, [beat])

        self.assertEqual(entries, [])

    def test_batches_across_multiple_beats(self):
        beat_a = BeatFactory()
        beat_b = BeatFactory()
        _sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        StakeFactory(
            beat=beat_a,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        StakeFactory(
            beat=beat_b,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )

        entries = player_pending_treasured_signoffs(player_data, [beat_a, beat_b])

        self.assertEqual({e.beat_id for e in entries}, {beat_a.pk, beat_b.pk})
        for entry in entries:
            self.assertEqual(entry.treasured_subject_ids, (treasured.pk,))

    def test_no_beats_returns_empty(self):
        _sheet, _tenure, player_data = _sheet_with_player()
        self.assertEqual(player_pending_treasured_signoffs(player_data, []), [])

    def test_retired_tenure_is_not_matched(self):
        """A treasured subject owned by a tenure that's no longer current is ignored."""
        from django.utils import timezone

        beat = BeatFactory()
        _sheet, tenure, player_data = _sheet_with_player()
        tenure.end_date = timezone.now()
        tenure.save(update_fields=["end_date"])
        TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )

        entries = player_pending_treasured_signoffs(player_data, [beat])

        self.assertEqual(entries, [])
