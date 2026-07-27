"""Tests for inactivity-detection services (#671).

Covers ``world.roster.services.activity``:
- decay_tier math (via CharacterSheet property)
- sweep_activity_states flip semantics (ACTIVE↔INACTIVE, HIATUS expiry, FROZEN skip)
- declare_hiatus / end_hiatus / freeze / unfreeze edge cases
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import (
    ActivityState,
    DecayTier,
    LifecycleState,
)
from world.roster.factories import RosterEntryFactory, RosterFactory, RosterTenureFactory
from world.roster.models.choices import ActivityRequirement, RosterType
from world.roster.seeds import ensure_rosters
from world.roster.services.activity import (
    FREEZE_COOLDOWN_DAYS,
    MAX_HIATUS_DAYS,
    FreezeError,
    HiatusError,
    declare_hiatus,
    end_hiatus,
    freeze_character,
    mark_character_active,
    set_lifecycle_state,
    sweep_activity_states,
    unfreeze_character,
)


def _build_sheet_with_tenure(
    *,
    requirement: str = ActivityRequirement.LOW,
    days_inactive: int = 0,
) -> tuple:
    """Create a CharacterSheet on a Roster with a current tenure.

    Backdates Account.last_login by ``days_inactive`` so ``decay_tier`` can
    be exercised directly.

    Returns ``(sheet, account, roster, entry)``.
    """
    # activity_requirement is authored per character on the ENTRY (#2728), not on
    # the shelf — a shelf-level value would be flattened the moment approval moved
    # everyone onto the Active roster.
    roster = RosterFactory(roster_type=RosterType.ACTIVE)
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(
        character_sheet=sheet,
        roster=roster,
        activity_requirement=requirement,
    )
    tenure = RosterTenureFactory(roster_entry=entry)
    account = tenure.player_data.account
    account.last_login = timezone.now() - timedelta(days=days_inactive)
    account.save(update_fields=["last_login"])
    return sheet, account, roster, entry


class DecayTierMathTests(TestCase):
    """Compute decay_tier from Account.last_login at the four threshold boundaries."""

    def test_fresh_returns_none(self):
        sheet, _, _, _ = _build_sheet_with_tenure(days_inactive=1)
        self.assertIsNone(sheet.decay_tier)

    def test_recent_inactive_at_14_days(self):
        sheet, _, _, _ = _build_sheet_with_tenure(days_inactive=14)
        self.assertEqual(sheet.decay_tier, DecayTier.RECENT_INACTIVE)

    def test_short_inactive_at_30_days(self):
        sheet, _, _, _ = _build_sheet_with_tenure(days_inactive=30)
        self.assertEqual(sheet.decay_tier, DecayTier.SHORT_INACTIVE)

    def test_long_inactive_at_90_days(self):
        sheet, _, _, _ = _build_sheet_with_tenure(days_inactive=90)
        self.assertEqual(sheet.decay_tier, DecayTier.LONG_INACTIVE)

    def test_dormant_at_365_days(self):
        sheet, _, _, _ = _build_sheet_with_tenure(days_inactive=365)
        self.assertEqual(sheet.decay_tier, DecayTier.DORMANT)


class IsDormantTests(TestCase):
    """is_dormant returns True for any non-ACTIVE OR non-ALIVE state."""

    def setUp(self):
        self.sheet, *_ = _build_sheet_with_tenure()

    def test_default_active_alive_is_not_dormant(self):
        self.assertFalse(self.sheet.is_dormant)

    def test_hiatus_is_dormant(self):
        self.sheet.activity_state = ActivityState.HIATUS
        self.assertTrue(self.sheet.is_dormant)

    def test_inactive_is_dormant(self):
        self.sheet.activity_state = ActivityState.INACTIVE
        self.assertTrue(self.sheet.is_dormant)

    def test_frozen_is_dormant(self):
        self.sheet.activity_state = ActivityState.FROZEN
        self.assertTrue(self.sheet.is_dormant)

    def test_dead_is_dormant_even_when_active(self):
        self.sheet.lifecycle_state = LifecycleState.DEAD
        self.assertTrue(self.sheet.is_dormant)

    def test_coma_is_dormant(self):
        self.sheet.lifecycle_state = LifecycleState.COMA
        self.assertTrue(self.sheet.is_dormant)


class SweepActivityStatesTests(TestCase):
    """sweep_activity_states cron behavior."""

    def setUp(self):
        # The sweep releases onto the Available shelf, so the canonical shelves must
        # exist. Production seeds them; an unseeded DB is a deployment error the
        # sweep is meant to surface loudly rather than paper over (#2728).
        ensure_rosters()

    def test_flips_active_to_inactive_at_30_days(self):
        sheet, *_ = _build_sheet_with_tenure(requirement=ActivityRequirement.LOW, days_inactive=30)
        sweep_activity_states()
        sheet.refresh_from_db()
        self.assertEqual(sheet.activity_state, ActivityState.INACTIVE)

    def test_the_sweep_no_longer_promotes_a_returning_player(self):
        """Promotion moved to the login/puppet path (#2728 §6).

        The sweep is demotion-only now, so it must NOT quietly reactivate an
        INACTIVE sheet — otherwise the event-driven path is untested dead weight
        and a returning player's promotion silently depends on cron timing again.
        """
        sheet, *_ = _build_sheet_with_tenure(requirement=ActivityRequirement.LOW, days_inactive=5)
        sheet.activity_state = ActivityState.INACTIVE
        sheet.save(update_fields=["activity_state"])

        sweep_activity_states()

        sheet.refresh_from_db()
        self.assertEqual(sheet.activity_state, ActivityState.INACTIVE)

    def test_mark_character_active_promotes_on_return(self):
        """The replacement path: puppeting IS the signal, so it flips immediately."""
        sheet, *_ = _build_sheet_with_tenure(requirement=ActivityRequirement.LOW, days_inactive=5)
        sheet.activity_state = ActivityState.INACTIVE
        sheet.save(update_fields=["activity_state"])

        self.assertTrue(mark_character_active(sheet))

        sheet.refresh_from_db()
        self.assertEqual(sheet.activity_state, ActivityState.ACTIVE)

    def test_mark_character_active_leaves_hiatus_and_frozen_alone(self):
        """Only INACTIVE is cron-inferred; the other two are deliberate states."""
        for state in (ActivityState.HIATUS, ActivityState.FROZEN):
            with self.subTest(state=state):
                sheet, *_ = _build_sheet_with_tenure(requirement=ActivityRequirement.LOW)
                sheet.activity_state = state
                sheet.save(update_fields=["activity_state"])

                self.assertFalse(mark_character_active(sheet))

                sheet.refresh_from_db()
                self.assertEqual(sheet.activity_state, state)

    def test_hiatus_expires_to_active(self):
        sheet, *_ = _build_sheet_with_tenure(requirement=ActivityRequirement.LOW, days_inactive=60)
        sheet.activity_state = ActivityState.HIATUS
        sheet.activity_state_until = timezone.now() - timedelta(days=1)
        sheet.save(update_fields=["activity_state", "activity_state_until"])
        sweep_activity_states()
        sheet.refresh_from_db()
        self.assertEqual(sheet.activity_state, ActivityState.ACTIVE)
        self.assertIsNone(sheet.activity_state_until)

    def test_expiring_hiatus_does_not_also_demote_in_the_same_tick(self):
        """A vacation must not cost you the character the moment it ends (#2728).

        The decay clock keeps running through a declared absence, so a sheet whose
        hiatus lapses is already well past the 30-day bar. If expiry and demotion
        ran in one tick, the player would be flagged INACTIVE — and a roster
        character auto-released — before they had any chance to log back in, which
        is exactly what declaring a hiatus is supposed to prevent. They get the
        cycle until the next sweep.
        """
        sheet, *_ = _build_sheet_with_tenure(requirement=ActivityRequirement.LOW, days_inactive=60)
        sheet.activity_state = ActivityState.HIATUS
        sheet.activity_state_until = timezone.now() - timedelta(days=1)
        sheet.save(update_fields=["activity_state", "activity_state_until"])

        sweep_activity_states()

        sheet.refresh_from_db()
        self.assertEqual(sheet.activity_state, ActivityState.ACTIVE)

    def test_hiatus_in_window_stays_hiatus(self):
        sheet, *_ = _build_sheet_with_tenure(requirement=ActivityRequirement.LOW, days_inactive=60)
        sheet.activity_state = ActivityState.HIATUS
        sheet.activity_state_until = timezone.now() + timedelta(days=7)
        sheet.save(update_fields=["activity_state", "activity_state_until"])
        sweep_activity_states()
        sheet.refresh_from_db()
        self.assertEqual(sheet.activity_state, ActivityState.HIATUS)

    def test_frozen_never_touched_by_cron(self):
        sheet, *_ = _build_sheet_with_tenure(requirement=ActivityRequirement.LOW, days_inactive=400)
        sheet.activity_state = ActivityState.FROZEN
        sheet.activity_state_until = timezone.now() + timedelta(days=20)
        sheet.save(update_fields=["activity_state", "activity_state_until"])
        sweep_activity_states()
        sheet.refresh_from_db()
        self.assertEqual(sheet.activity_state, ActivityState.FROZEN)

    def test_none_requirement_is_still_flagged_inactive(self):
        """§4: the flag is universal — NONE no longer means "never swept".

        Every character goes INACTIVE at 30 days so nothing accrues income or takes
        decay for someone who isn't there. What NONE buys is exemption from
        *release*, not from the flag.
        """
        sheet, *_ = _build_sheet_with_tenure(
            requirement=ActivityRequirement.NONE, days_inactive=400
        )

        sweep_activity_states()

        sheet.refresh_from_db()
        self.assertEqual(sheet.activity_state, ActivityState.INACTIVE)


class HiatusServiceTests(TestCase):
    def setUp(self):
        self.sheet, *_ = _build_sheet_with_tenure()

    def test_declare_hiatus_sets_state(self):
        end = timezone.now() + timedelta(days=14)
        declare_hiatus(self.sheet, end)
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.activity_state, ActivityState.HIATUS)
        self.assertEqual(self.sheet.activity_state_until, end)

    def test_declare_hiatus_rejects_past_date(self):
        end = timezone.now() - timedelta(days=1)
        with self.assertRaises(HiatusError):
            declare_hiatus(self.sheet, end)

    def test_declare_hiatus_rejects_over_max(self):
        end = timezone.now() + timedelta(days=MAX_HIATUS_DAYS + 1)
        with self.assertRaises(HiatusError):
            declare_hiatus(self.sheet, end)

    def test_end_hiatus_flips_active(self):
        self.sheet.activity_state = ActivityState.HIATUS
        self.sheet.activity_state_until = timezone.now() + timedelta(days=7)
        self.sheet.save()
        end_hiatus(self.sheet)
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.activity_state, ActivityState.ACTIVE)
        self.assertIsNone(self.sheet.activity_state_until)

    def test_end_hiatus_rejects_non_hiatus(self):
        with self.assertRaises(HiatusError):
            end_hiatus(self.sheet)


class FreezeUnfreezeTests(TestCase):
    def setUp(self):
        self.sheet, *_ = _build_sheet_with_tenure()
        self.sheet.is_oc = True
        self.sheet.save()

    def test_freeze_sets_state_and_cooldown(self):
        before = timezone.now()
        freeze_character(self.sheet)
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.activity_state, ActivityState.FROZEN)
        expected_min = before + timedelta(days=FREEZE_COOLDOWN_DAYS)
        # Tolerate small clock drift between before/after the call
        self.assertGreaterEqual(
            self.sheet.activity_state_until,
            expected_min - timedelta(seconds=5),
        )

    def test_freeze_rejects_non_oc(self):
        self.sheet.is_oc = False
        self.sheet.save()
        with self.assertRaises(FreezeError):
            freeze_character(self.sheet)

    def test_freeze_rejects_non_active(self):
        self.sheet.activity_state = ActivityState.HIATUS
        self.sheet.save()
        with self.assertRaises(FreezeError):
            freeze_character(self.sheet)

    def test_freeze_rejects_dead(self):
        self.sheet.lifecycle_state = LifecycleState.DEAD
        self.sheet.save()
        with self.assertRaises(FreezeError):
            freeze_character(self.sheet)

    def test_unfreeze_blocked_during_cooldown(self):
        freeze_character(self.sheet)
        self.sheet.refresh_from_db()
        with self.assertRaises(FreezeError):
            unfreeze_character(self.sheet)

    def test_unfreeze_allowed_after_cooldown(self):
        freeze_character(self.sheet)
        self.sheet.refresh_from_db()
        # Backdate the cooldown to simulate cooldown expiry.
        self.sheet.activity_state_until = timezone.now() - timedelta(seconds=1)
        self.sheet.save(update_fields=["activity_state_until"])
        unfreeze_character(self.sheet)
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.activity_state, ActivityState.ACTIVE)


class SetLifecycleStateTests(TestCase):
    def setUp(self):
        self.sheet, *_ = _build_sheet_with_tenure()

    def test_sets_dead(self):
        set_lifecycle_state(self.sheet, LifecycleState.DEAD)
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.lifecycle_state, LifecycleState.DEAD)
        self.assertIsNotNone(self.sheet.lifecycle_state_at)

    def test_rejects_invalid_state(self):
        from world.roster.services.activity import LifecycleStateError

        with self.assertRaises(LifecycleStateError):
            set_lifecycle_state(self.sheet, "BANANA")
