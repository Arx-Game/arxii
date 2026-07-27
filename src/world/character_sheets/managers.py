"""Shared activity/absence vocabulary for CharacterSheet (#2728 §5).

Three systems used to each answer "is this character absent?" from different
inputs — ``mothball_services`` read raw ``decay_tier`` day-counts, the sanctum
services read the ``is_dormant`` flags, and applications read ``Roster``
membership. Three definitions of one concept drift as consumers land. These
manager methods are the single vocabulary consumers ask instead.

The tier is **derived, not stored**: it is a pure function of timestamps we
already keep (``Account.last_login`` and ``RosterEntry.last_puppeted``), so a
stored copy would need maintaining on both the cron path and the login path.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone
from evennia.utils.idmapper.manager import SharedMemoryManager

from world.character_sheets.types import (
    DECAY_TIER_THRESHOLDS_DAYS,
    ActivityState,
    DecayTier,
    LifecycleState,
)


class CharacterSheetQuerySet(models.QuerySet):
    """Absence vocabulary. See ``managers`` module docstring for why it lives here."""

    def active(self) -> CharacterSheetQuerySet:
        """Playable and being played — the queryset form of ``not is_dormant``."""
        return self.filter(
            activity_state=ActivityState.ACTIVE,
            lifecycle_state=LifecycleState.ALIVE,
        )

    def dormant(self) -> CharacterSheetQuerySet:
        """Neither active nor claimable — any non-ACTIVE OOC or non-ALIVE IC state.

        The exact complement of ``active()``: ``exclude()`` with both conditions
        negates the conjunction, so a sheet failing *either* is dormant.
        """
        return self.exclude(
            activity_state=ActivityState.ACTIVE,
            lifecycle_state=LifecycleState.ALIVE,
        )

    def claimable(self) -> CharacterSheetQuerySet:
        """Free for someone to apply to: on an applications-open roster, unplayed.

        Delegates to ``RosterEntryQuerySet.available_characters()`` rather than
        restating the predicate. Two copies of "what is claimable" is precisely
        the drift this vocabulary exists to end, and that one is already the
        definition the application surface uses. Passed as a subquery, never a
        materialised list.
        """
        from world.roster.models import RosterEntry  # noqa: PLC0415

        return self.filter(roster_entry__in=RosterEntry.objects.available_characters())

    def inactive_at_least(self, tier: DecayTier) -> CharacterSheetQuerySet:
        """Sheets whose newest activity signal is at least ``tier``'s age.

        The DB-level counterpart of ``CharacterSheet.decay_tier``, for consumers
        like mothballing that legitimately want a longer bar than the 30-day
        flag. Kept in lockstep with ``_last_activity_signal_at`` — same signals,
        same per-requirement rules:

        * ``LOW`` — account login only.
        * ``HIGH`` / ``NONE`` — newest of account login and ``last_puppeted``.
        * No roster entry — the creating account's login.

        Expressed as "every signal is old" rather than "the newest signal is
        old". They are equivalent (``MAX(xs) <= cutoff`` iff every ``x <=
        cutoff``), and the former avoids ``Greatest``, whose NULL handling
        differs between PostgreSQL and SQLite — the fast test tier would
        disagree with production.

        A sheet with no signal at all is NOT inactive, matching ``decay_tier``
        returning None rather than a tier.
        """
        from world.roster.models.choices import ActivityRequirement  # noqa: PLC0415
        from world.roster.models.tenures import RosterTenure  # noqa: PLC0415

        cutoff = timezone.now() - timedelta(days=DECAY_TIER_THRESHOLDS_DAYS[tier])
        current_login = models.Subquery(
            RosterTenure.objects.filter(
                roster_entry=models.OuterRef("roster_entry"),
                end_date__isnull=True,
            )
            .order_by("-start_date")
            .values("player_data__account__last_login")[:1],
        )
        annotated = self.annotate(_current_tenure_login=current_login)

        has_entry = Q(roster_entry__isnull=False)
        is_low = Q(roster_entry__activity_requirement=ActivityRequirement.LOW)

        # LOW: login is the only signal, so a missing login means no signal at all.
        low_stale = has_entry & is_low & Q(_current_tenure_login__lte=cutoff)

        # HIGH/NONE: both signals count. Each is stale if absent or old, but at
        # least one must be present or there is no signal to have gone stale.
        login_stale = Q(_current_tenure_login__isnull=True) | Q(
            _current_tenure_login__lte=cutoff,
        )
        puppet_stale = Q(roster_entry__last_puppeted__isnull=True) | Q(
            roster_entry__last_puppeted__lte=cutoff,
        )
        any_signal = Q(_current_tenure_login__isnull=False) | Q(
            roster_entry__last_puppeted__isnull=False,
        )
        other_stale = has_entry & ~is_low & login_stale & puppet_stale & any_signal

        # No roster entry: fall back to the creating account. A null login is
        # excluded by the comparison itself.
        no_entry_stale = Q(roster_entry__isnull=True) & Q(created_by__last_login__lte=cutoff)

        return annotated.filter(low_stale | other_stale | no_entry_stale)


class CharacterSheetManager(SharedMemoryManager, models.Manager):
    """CharacterSheet's manager, carrying the absence vocabulary.

    Based on ``SharedMemoryManager`` so ``.get(pk=N)`` keeps hitting Evennia's
    identity map (ADR-0008). Deliberately NOT ``ArxSharedMemoryManager``: that
    adds ``cached_all()``, and a full-table cache on a playerbase-scoped table
    is a footgun rather than a feature.
    """

    def get_queryset(self) -> CharacterSheetQuerySet:
        return CharacterSheetQuerySet(self.model, using=self._db)

    def active(self) -> CharacterSheetQuerySet:
        return self.get_queryset().active()

    def dormant(self) -> CharacterSheetQuerySet:
        return self.get_queryset().dormant()

    def claimable(self) -> CharacterSheetQuerySet:
        return self.get_queryset().claimable()

    def inactive_at_least(self, tier: DecayTier) -> CharacterSheetQuerySet:
        return self.get_queryset().inactive_at_least(tier)
