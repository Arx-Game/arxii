"""Auto-release of inactive roster characters (#2728 §7).

The flag and the release have deliberately different scopes, and conflating them
is the main thing these tests guard. The inactivity flag is broad because its job
is to stop income accruing and decay biting for someone who isn't there. The
release is narrow because taking a character away is only justified when someone
else is waiting for it — true of a roster character whose authored stories block
on its absence, not of a player's own creation.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import ActivityState
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models import RosterApplication
from world.roster.models.choices import ActivityRequirement, RosterType
from world.roster.seeds import ensure_rosters
from world.roster.services.activity import sweep_activity_states


def _played_character(
    *,
    requirement: str = ActivityRequirement.HIGH,
    days_inactive: int = 400,
    is_oc: bool = False,
    shelf: str = RosterType.ACTIVE,
):
    """A character on ``shelf`` with an open tenure and a stale login."""
    sheet = CharacterSheetFactory(is_oc=is_oc)
    entry = RosterEntryFactory(
        character_sheet=sheet,
        roster=RosterFactory(roster_type=shelf),
        activity_requirement=requirement,
    )
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    account.last_login = timezone.now() - timedelta(days=days_inactive)
    account.save(update_fields=["last_login"])
    return sheet, entry, tenure


class AutoReleaseScopeTests(TestCase):
    """Who gets released, and — more importantly — who does not."""

    def setUp(self):
        ensure_rosters()

    def _sweep_and_reload(self, sheet, entry, tenure):
        sweep_activity_states()
        sheet.refresh_from_db()
        entry.refresh_from_db()
        tenure.refresh_from_db()

    def test_high_requirement_roster_character_is_released(self):
        sheet, entry, tenure = _played_character(requirement=ActivityRequirement.HIGH)

        self._sweep_and_reload(sheet, entry, tenure)

        self.assertEqual(sheet.activity_state, ActivityState.INACTIVE)
        self.assertIsNotNone(tenure.end_date)
        self.assertEqual(entry.roster.roster_type, RosterType.AVAILABLE)

    def test_low_requirement_roster_character_is_released(self):
        sheet, entry, tenure = _played_character(requirement=ActivityRequirement.LOW)

        self._sweep_and_reload(sheet, entry, tenure)

        self.assertIsNotNone(tenure.end_date)
        self.assertEqual(entry.roster.roster_type, RosterType.AVAILABLE)

    def test_none_requirement_is_flagged_but_never_released(self):
        """The authored "carries no activity expectation" tier."""
        sheet, entry, tenure = _played_character(requirement=ActivityRequirement.NONE)

        self._sweep_and_reload(sheet, entry, tenure)

        self.assertEqual(sheet.activity_state, ActivityState.INACTIVE)
        self.assertIsNone(tenure.end_date)
        self.assertEqual(entry.roster.roster_type, RosterType.ACTIVE)

    def test_an_oc_is_flagged_but_never_released(self):
        """A player's own character is theirs, whatever its requirement says."""
        sheet, entry, tenure = _played_character(
            requirement=ActivityRequirement.HIGH,
            is_oc=True,
        )

        self._sweep_and_reload(sheet, entry, tenure)

        self.assertEqual(sheet.activity_state, ActivityState.INACTIVE)
        self.assertIsNone(tenure.end_date)

    def test_an_npc_is_never_even_examined(self):
        """Excluded by shelf, not by a special case (#2728 §10)."""
        sheet, entry, tenure = _played_character(
            requirement=ActivityRequirement.HIGH,
            shelf=RosterType.NPC,
        )

        self._sweep_and_reload(sheet, entry, tenure)

        self.assertEqual(sheet.activity_state, ActivityState.ACTIVE)
        self.assertIsNone(tenure.end_date)

    def test_hiatus_exempts_from_release(self):
        sheet, entry, tenure = _played_character(requirement=ActivityRequirement.HIGH)
        sheet.activity_state = ActivityState.HIATUS
        sheet.activity_state_until = timezone.now() + timedelta(days=30)
        sheet.save(update_fields=["activity_state", "activity_state_until"])

        self._sweep_and_reload(sheet, entry, tenure)

        self.assertEqual(sheet.activity_state, ActivityState.HIATUS)
        self.assertIsNone(tenure.end_date)

    def test_a_recently_active_character_is_untouched(self):
        sheet, entry, tenure = _played_character(days_inactive=3)

        self._sweep_and_reload(sheet, entry, tenure)

        self.assertEqual(sheet.activity_state, ActivityState.ACTIVE)
        self.assertIsNone(tenure.end_date)

    def test_telemetry_counts_the_release(self):
        _played_character(requirement=ActivityRequirement.HIGH)

        result = sweep_activity_states()

        self.assertEqual(result["flipped_to_inactive"], 1)
        self.assertEqual(result["released"], 1)


class ReleasedCharacterIsClaimableTests(TestCase):
    def setUp(self):
        ensure_rosters()

    def test_a_released_character_can_be_applied_for_again(self):
        """The point of releasing: somebody else is waiting for it."""
        from world.character_sheets.models import CharacterSheet

        sheet, entry, _ = _played_character(requirement=ActivityRequirement.HIGH)

        sweep_activity_states()

        entry.refresh_from_db()
        self.assertTrue(entry.accepts_applications)
        self.assertIn(
            sheet.pk,
            set(CharacterSheet.objects.claimable().values_list("pk", flat=True)),
        )


class ReturningPlayerReopensTenureTests(TestCase):
    """Approval is the decision point; a returning player is re-seated, not renumbered."""

    def setUp(self):
        ensure_rosters()

    def test_the_original_player_keeps_their_player_number(self):
        sheet, entry, tenure = _played_character(requirement=ActivityRequirement.HIGH)
        original_player = tenure.player_data
        original_number = tenure.player_number
        original_pk = tenure.pk

        sweep_activity_states()

        application = RosterApplication.objects.create(
            player_data=original_player,
            character=sheet,
            application_text="I am back and would like to pick this up again.",
        )
        reopened = application.approve(PlayerDataFactory(account__is_staff=True))

        self.assertEqual(reopened.pk, original_pk)
        self.assertEqual(reopened.player_number, original_number)
        self.assertIsNone(reopened.end_date)
        self.assertEqual(entry.tenures.count(), 1)

    def test_a_different_player_gets_the_next_number(self):
        sheet, entry, tenure = _played_character(requirement=ActivityRequirement.HIGH)
        first_number = tenure.player_number

        sweep_activity_states()

        application = RosterApplication.objects.create(
            player_data=PlayerDataFactory(),
            character=sheet,
            application_text="I would like to take this character on.",
        )
        new_tenure = application.approve(PlayerDataFactory(account__is_staff=True))

        self.assertNotEqual(new_tenure.pk, tenure.pk)
        self.assertEqual(new_tenure.player_number, first_number + 1)
        self.assertEqual(entry.tenures.count(), 2)

    def test_approval_moves_the_character_onto_the_active_shelf(self):
        """It was offered from Available; someone is playing it now."""
        sheet, entry, _ = _played_character(requirement=ActivityRequirement.HIGH)
        sweep_activity_states()
        entry.refresh_from_db()
        self.assertEqual(entry.roster.roster_type, RosterType.AVAILABLE)

        application = RosterApplication.objects.create(
            player_data=PlayerDataFactory(),
            character=sheet,
            application_text="Applying for this character now that it is free.",
        )
        application.approve(PlayerDataFactory(account__is_staff=True))

        entry.refresh_from_db()
        self.assertEqual(entry.roster.roster_type, RosterType.ACTIVE)
