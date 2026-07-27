"""The shared absence vocabulary on CharacterSheet.objects (#2728 §5).

The load-bearing test here is ``InactiveAtLeastMatchesDecayTierTests``:
``inactive_at_least`` is a SQL twin of the Python ``decay_tier`` property, and
two implementations of one rule is exactly the drift this vocabulary exists to
end. It is pinned by parity against the property, not by hand-written expected
sets, so a change to either side that the other doesn't follow fails.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.character_sheets.types import (
    DECAY_TIER_THRESHOLDS_DAYS,
    ActivityState,
    DecayTier,
    LifecycleState,
)
from world.roster.factories import RosterEntryFactory, RosterFactory, RosterTenureFactory
from world.roster.models.choices import ActivityRequirement, RosterType


def _sheet_with_tenure(
    *,
    requirement: str = ActivityRequirement.LOW,
    days_since_login: int | None = 0,
    days_since_puppet: int | None = None,
) -> CharacterSheet:
    """A sheet on a roster of ``requirement`` with backdated activity signals.

    ``None`` for either day-count leaves that signal unset, so the no-signal and
    single-signal cases are expressible.
    """
    roster = RosterFactory(roster_type=RosterType.ACTIVE)
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(
        character_sheet=sheet,
        roster=roster,
        activity_requirement=requirement,
    )
    tenure = RosterTenureFactory(roster_entry=entry)

    account = tenure.player_data.account
    account.last_login = (
        None if days_since_login is None else timezone.now() - timedelta(days=days_since_login)
    )
    account.save(update_fields=["last_login"])

    if days_since_puppet is not None:
        entry.last_puppeted = timezone.now() - timedelta(days=days_since_puppet)
        entry.save(update_fields=["last_puppeted"])
    return sheet


class ActiveAndDormantTests(TestCase):
    """active() and dormant() partition the table on the two state columns."""

    def test_active_requires_both_axes(self):
        alive = CharacterSheetFactory()
        on_hiatus = CharacterSheetFactory(activity_state=ActivityState.HIATUS)
        dead = CharacterSheetFactory(lifecycle_state=LifecycleState.DEAD)

        active_pks = set(CharacterSheet.objects.active().values_list("pk", flat=True))

        self.assertIn(alive.pk, active_pks)
        self.assertNotIn(on_hiatus.pk, active_pks)
        self.assertNotIn(dead.pk, active_pks)

    def test_dormant_is_the_exact_complement_of_active(self):
        """Not merely 'both disjoint' — every row must land in exactly one."""
        CharacterSheetFactory()
        CharacterSheetFactory(activity_state=ActivityState.INACTIVE)
        CharacterSheetFactory(lifecycle_state=LifecycleState.UNKNOWN)
        CharacterSheetFactory(
            activity_state=ActivityState.FROZEN,
            lifecycle_state=LifecycleState.DEAD,
        )

        active_pks = set(CharacterSheet.objects.active().values_list("pk", flat=True))
        dormant_pks = set(CharacterSheet.objects.dormant().values_list("pk", flat=True))
        all_pks = set(CharacterSheet.objects.values_list("pk", flat=True))

        self.assertEqual(active_pks | dormant_pks, all_pks)
        self.assertEqual(active_pks & dormant_pks, set())

    def test_new_unknown_lifecycle_state_counts_as_dormant(self):
        """UNKNOWN split from CAPTURED (#2728 §2) must not read as present."""
        missing = CharacterSheetFactory(lifecycle_state=LifecycleState.UNKNOWN)

        self.assertIn(
            missing.pk,
            set(CharacterSheet.objects.dormant().values_list("pk", flat=True)),
        )
        self.assertTrue(missing.is_dormant)


class ClaimableTests(TestCase):
    def test_claimable_excludes_a_character_someone_is_playing(self):
        open_roster = RosterFactory(
            roster_type=RosterType.AVAILABLE,
            allow_applications=True,
        )
        free = CharacterSheetFactory()
        RosterEntryFactory(character_sheet=free, roster=open_roster)

        taken = CharacterSheetFactory()
        taken_entry = RosterEntryFactory(character_sheet=taken, roster=open_roster)
        RosterTenureFactory(roster_entry=taken_entry, end_date=None)

        claimable_pks = set(CharacterSheet.objects.claimable().values_list("pk", flat=True))

        self.assertIn(free.pk, claimable_pks)
        self.assertNotIn(taken.pk, claimable_pks)

    def test_claimable_excludes_a_closed_roster(self):
        """NPCs sit on a shelf with allow_applications=False (#2728 §10)."""
        npc_roster = RosterFactory(roster_type=RosterType.NPC, allow_applications=False)
        npc = CharacterSheetFactory()
        RosterEntryFactory(character_sheet=npc, roster=npc_roster)

        self.assertNotIn(
            npc.pk,
            set(CharacterSheet.objects.claimable().values_list("pk", flat=True)),
        )


class InactiveAtLeastMatchesDecayTierTests(TestCase):
    """inactive_at_least(tier) must agree with the decay_tier property, always."""

    def test_parity_across_every_tier_boundary(self):
        ages = [0, 13, 14, 29, 30, 89, 90, 364, 365, 400]
        sheets = {age: _sheet_with_tenure(days_since_login=age) for age in ages}

        for tier, threshold in DECAY_TIER_THRESHOLDS_DAYS.items():
            matched = set(
                CharacterSheet.objects.inactive_at_least(tier).values_list("pk", flat=True),
            )
            for age, sheet in sheets.items():
                with self.subTest(tier=tier, age=age):
                    self.assertEqual(
                        sheet.pk in matched,
                        age >= threshold,
                        f"{tier} at {age}d disagreed with the {threshold}d threshold",
                    )

    def test_parity_with_the_property_itself(self):
        """Cross-check against decay_tier rather than against restated thresholds."""
        for age in (0, 14, 30, 90, 365):
            sheet = _sheet_with_tenure(days_since_login=age)
            for tier, threshold in DECAY_TIER_THRESHOLDS_DAYS.items():
                in_queryset = (
                    CharacterSheet.objects.filter(pk=sheet.pk).inactive_at_least(tier).exists()
                )
                property_tier = sheet.decay_tier
                property_says = (
                    property_tier is not None
                    and DECAY_TIER_THRESHOLDS_DAYS[property_tier] >= threshold
                )
                with self.subTest(age=age, tier=tier):
                    self.assertEqual(in_queryset, property_says)


class InactiveAtLeastSignalRulesTests(TestCase):
    """Which signals count is per-requirement, and must mirror the property."""

    def test_high_requirement_counts_puppeting_as_activity(self):
        """Stale login but recent IC action: present, so not inactive."""
        sheet = _sheet_with_tenure(
            requirement=ActivityRequirement.HIGH,
            days_since_login=200,
            days_since_puppet=1,
        )

        matched = CharacterSheet.objects.filter(pk=sheet.pk).inactive_at_least(
            DecayTier.SHORT_INACTIVE,
        )

        self.assertFalse(matched.exists())
        self.assertIsNone(sheet.decay_tier)

    def test_low_requirement_ignores_puppeting(self):
        """LOW keys on login only, so recent puppeting must not rescue it."""
        sheet = _sheet_with_tenure(
            requirement=ActivityRequirement.LOW,
            days_since_login=200,
            days_since_puppet=1,
        )

        matched = CharacterSheet.objects.filter(pk=sheet.pk).inactive_at_least(
            DecayTier.SHORT_INACTIVE,
        )

        self.assertTrue(matched.exists())
        self.assertEqual(sheet.decay_tier, DecayTier.LONG_INACTIVE)

    def test_a_sheet_with_no_signal_at_all_is_not_inactive(self):
        """decay_tier returns None rather than a tier; the queryset must agree."""
        sheet = _sheet_with_tenure(
            requirement=ActivityRequirement.HIGH,
            days_since_login=None,
        )

        matched = CharacterSheet.objects.filter(pk=sheet.pk).inactive_at_least(
            DecayTier.RECENT_INACTIVE,
        )

        self.assertFalse(matched.exists())
        self.assertIsNone(sheet.decay_tier)


class ManagerPreservesIdentityMapTests(TestCase):
    """The custom manager must not cost CharacterSheet its idmapper caching."""

    def test_get_by_pk_returns_the_identical_cached_instance(self):
        sheet = CharacterSheetFactory()

        first = CharacterSheet.objects.get(pk=sheet.pk)
        second = CharacterSheet.objects.get(pk=sheet.pk)

        self.assertIs(first, second)
