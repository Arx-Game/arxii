"""Tests for the #1771 task 5 sign-off + GM-availability services.

``grant_treasured_signoff`` / ``withdraw_treasured_signoff`` live in
``world.stories.services.boundaries`` (not ``world.boundaries``) because they
mutate the stories-owned ``TreasuredSignoff`` model — stories depends on
boundaries, never the reverse (ADR-0010). ``stake_availability`` lives there
too since it reuses the stories-owned ``check_stake_boundaries``.
"""

from django.test import TestCase
from django.utils import timezone

from world.boundaries.constants import BoundaryKind
from world.boundaries.factories import (
    ContentThemeFactory,
    PlayerBoundaryFactory,
    TreasuredSubjectFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.stories.constants import StakeSubjectKind
from world.stories.factories import BeatFactory, StakeFactory, StakeTemplateFactory
from world.stories.models import TreasuredSignoff
from world.stories.services.boundaries import (
    check_stake_boundaries,
    grant_treasured_signoff,
    stake_availability,
    withdraw_treasured_signoff,
)


def _sheet_with_player():
    """A CharacterSheet with a live current tenure (roster_entry -> tenure -> player_data)."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    player_data = PlayerDataFactory()
    tenure = RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return sheet, tenure, player_data


class GrantTreasuredSignoffTests(TestCase):
    def test_grant_creates_a_new_active_signoff(self):
        beat = BeatFactory()
        _sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(owner=tenure)

        signoff = grant_treasured_signoff(beat, player_data, treasured)

        self.assertTrue(signoff.active)
        self.assertEqual(TreasuredSignoff.objects.count(), 1)

    def test_grant_clears_the_requires_signoff_gate(self):
        beat = BeatFactory()
        sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        stake = StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )

        before = check_stake_boundaries([stake], [sheet])
        self.assertIn(sheet.pk, before.requires_signoff)

        grant_treasured_signoff(beat, player_data, treasured)

        after = check_stake_boundaries([stake], [sheet])
        self.assertNotIn(sheet.pk, after.requires_signoff)
        self.assertTrue(after.cleared)

    def test_grant_reactivates_a_withdrawn_signoff_instead_of_duplicating(self):
        beat = BeatFactory()
        _sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(owner=tenure)
        first = grant_treasured_signoff(beat, player_data, treasured)
        withdraw_treasured_signoff(first)
        self.assertFalse(first.active)

        second = grant_treasured_signoff(beat, player_data, treasured)

        self.assertEqual(second.pk, first.pk)
        self.assertTrue(second.active)
        self.assertEqual(TreasuredSignoff.objects.count(), 1)

    def test_grant_is_idempotent_when_already_active(self):
        beat = BeatFactory()
        _sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(owner=tenure)
        first = grant_treasured_signoff(beat, player_data, treasured)

        second = grant_treasured_signoff(beat, player_data, treasured)

        self.assertEqual(second.pk, first.pk)
        self.assertTrue(second.active)
        self.assertEqual(TreasuredSignoff.objects.count(), 1)


class WithdrawTreasuredSignoffTests(TestCase):
    def test_withdraw_sets_withdrawn_at_and_flips_active_false(self):
        beat = BeatFactory()
        _sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(owner=tenure)
        signoff = grant_treasured_signoff(beat, player_data, treasured)

        withdraw_treasured_signoff(signoff)

        self.assertFalse(signoff.active)
        signoff.refresh_from_db()
        self.assertIsNotNone(signoff.withdrawn_at)

    def test_withdraw_reopens_the_requires_signoff_gate(self):
        beat = BeatFactory()
        sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        stake = StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        signoff = grant_treasured_signoff(beat, player_data, treasured)
        self.assertTrue(check_stake_boundaries([stake], [sheet]).cleared)

        withdraw_treasured_signoff(signoff)

        report = check_stake_boundaries([stake], [sheet])
        self.assertIn(sheet.pk, report.requires_signoff)
        self.assertFalse(report.cleared)

    def test_withdraw_is_idempotent(self):
        beat = BeatFactory()
        _sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(owner=tenure)
        signoff = grant_treasured_signoff(beat, player_data, treasured)
        withdraw_treasured_signoff(signoff)
        first_withdrawn_at = signoff.withdrawn_at

        withdraw_treasured_signoff(signoff)

        self.assertEqual(signoff.withdrawn_at, first_withdrawn_at)


class StakeAvailabilityTests(TestCase):
    def test_tallies_available_blocked_and_needs_signoff(self):
        beat = BeatFactory()
        sheet, tenure, player_data = _sheet_with_player()

        # Ordinary stake: no boundary hit at all -> available.
        StakeFactory(beat=beat, template=None, subject_label="Ordinary wager")

        # Treasured stake without a signoff -> needs_signoff.
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

        # Hard-lined stake -> blocked.
        theme = ContentThemeFactory()
        template = StakeTemplateFactory()
        template.content_themes.add(theme)
        PlayerBoundaryFactory(owner=player_data, kind=BoundaryKind.HARD_LINE, theme=theme)
        StakeFactory(beat=beat, template=template)

        availability = stake_availability(beat, [sheet])

        self.assertEqual(availability.available, 1)
        self.assertEqual(availability.needs_signoff, 1)
        self.assertEqual(availability.blocked, 1)

    def test_needs_signoff_stake_becomes_available_after_grant(self):
        beat = BeatFactory()
        sheet, tenure, player_data = _sheet_with_player()
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

        before = stake_availability(beat, [sheet])
        self.assertEqual(before.needs_signoff, 1)
        self.assertEqual(before.available, 0)

        grant_treasured_signoff(beat, player_data, treasured)

        after = stake_availability(beat, [sheet])
        self.assertEqual(after.needs_signoff, 0)
        self.assertEqual(after.available, 1)

    def test_no_stakes_on_beat_returns_all_zero_counts(self):
        beat = BeatFactory()
        sheet, _tenure, _player_data = _sheet_with_player()

        availability = stake_availability(beat, [sheet])

        self.assertEqual(availability.available, 0)
        self.assertEqual(availability.blocked, 0)
        self.assertEqual(availability.needs_signoff, 0)

    def test_availability_never_leaks_reason_or_owner_fields(self):
        """The value object's own field set is the leak guard: no reason/owner field exists."""
        import dataclasses

        beat = BeatFactory()
        field_names = {f.name for f in dataclasses.fields(stake_availability(beat, []))}
        self.assertEqual(field_names, {"available", "blocked", "needs_signoff"})

    def test_timezone_import_used_by_withdraw(self):
        """Sanity: withdrawn_at is a real timestamp near now (guards a no-op regression)."""
        beat = BeatFactory()
        _sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(owner=tenure)
        signoff = grant_treasured_signoff(beat, player_data, treasured)

        withdraw_treasured_signoff(signoff)

        self.assertLessEqual((timezone.now() - signoff.withdrawn_at).total_seconds(), 5)
