"""Tests for OC cap enforcement (#671 Phase 6)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.services import (
    DEFAULT_OC_CAP,
    OCCapError,
    count_active_ocs,
    enforce_oc_cap,
)
from world.character_sheets.types import ActivityState, LifecycleState
from world.roster.factories import RosterEntryFactory, RosterFactory


def _make_oc(account, *, allow_applications: bool = False, **sheet_kwargs):
    """Build an OC owned by ``account`` on a Roster matching ``allow_applications``."""
    roster = RosterFactory(allow_applications=allow_applications)
    sheet = CharacterSheetFactory(is_oc=True, created_by=account, **sheet_kwargs)
    RosterEntryFactory(character_sheet=sheet, roster=roster)
    return sheet


class CountActiveOCsTests(TestCase):
    def test_empty_account_returns_zero(self):
        account = AccountFactory()
        self.assertEqual(count_active_ocs(account), 0)

    def test_basic_oc_counts(self):
        account = AccountFactory()
        _make_oc(account)
        self.assertEqual(count_active_ocs(account), 1)

    def test_converted_to_public_roster_doesnt_count(self):
        account = AccountFactory()
        _make_oc(account, allow_applications=True)  # converted to community
        self.assertEqual(count_active_ocs(account), 0)

    def test_frozen_doesnt_count(self):
        account = AccountFactory()
        _make_oc(account, activity_state=ActivityState.FROZEN)
        self.assertEqual(count_active_ocs(account), 0)

    def test_dead_doesnt_count(self):
        account = AccountFactory()
        _make_oc(account, lifecycle_state=LifecycleState.DEAD)
        self.assertEqual(count_active_ocs(account), 0)

    def test_retired_doesnt_count(self):
        account = AccountFactory()
        _make_oc(account, lifecycle_state=LifecycleState.RETIRED)
        self.assertEqual(count_active_ocs(account), 0)

    def test_hiatus_still_counts(self):
        # Hiatus = "I'm away for a while", slot still held.
        account = AccountFactory()
        _make_oc(account, activity_state=ActivityState.HIATUS)
        self.assertEqual(count_active_ocs(account), 1)

    def test_inactive_still_counts(self):
        # Inactive auto-flip doesn't free the slot.
        account = AccountFactory()
        _make_oc(account, activity_state=ActivityState.INACTIVE)
        self.assertEqual(count_active_ocs(account), 1)

    def test_other_accounts_ocs_dont_count(self):
        account = AccountFactory()
        other = AccountFactory()
        _make_oc(other)
        self.assertEqual(count_active_ocs(account), 0)


class EnforceOCCapTests(TestCase):
    def test_under_cap_passes(self):
        account = AccountFactory()
        _make_oc(account)
        _make_oc(account)
        enforce_oc_cap(account)  # 2 < 3 default cap

    def test_at_cap_raises(self):
        account = AccountFactory()
        for _ in range(DEFAULT_OC_CAP):
            _make_oc(account)
        with self.assertRaises(OCCapError) as ctx:
            enforce_oc_cap(account)
        self.assertIn("OCs", ctx.exception.user_message)

    def test_staff_bypass(self):
        account = AccountFactory(is_staff=True)
        for _ in range(DEFAULT_OC_CAP + 5):
            _make_oc(account)
        enforce_oc_cap(account)  # staff has no cap

    def test_custom_cap(self):
        account = AccountFactory()
        _make_oc(account)
        enforce_oc_cap(account, cap=2)  # 1 < 2 → passes
        _make_oc(account)
        with self.assertRaises(OCCapError):
            enforce_oc_cap(account, cap=2)
