"""Dormancy (#5069 slice 3): a house nobody plays goes dormant; coin freezes, land runs.

The maintainer's rulings (2026-11-11):

- Presence is the test, never actions. A house is awake while any of its members'
  characters sits on the roster under an account that logged in within
  ``DominionConfig.dormancy_window_days``. A lull inside the window still accrues,
  uncapped: people expect things to gather while they are away a few weeks.
- A house with no played character goes dormant. Its income streams stop accruing,
  so nobody apping into an empty house finds a hoard. Staff-made houses with roster
  characters nobody has taken up (House Katta) are the case this exists for.
- Dormancy freezes accumulators, never equilibria: population, prosperity and the
  land run by formula whether or not anyone plays, so a regional event can strike a
  dormant house's land and the land can recover.
- The tick budget: going dormant is one set-based statement a week; waking is
  event-driven (a login, a roster approval), one statement each. Bulk SQL bypasses
  the identity map, so every write here flushes the organizations it touched.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from evennia_extensions.models import PlayerData
from world.societies.houses.models import DominionConfig
from world.societies.models import Organization, OrganizationMembership

_PLAYED_TENURE = "persona__character_sheet__roster_entry__tenures"


def _played_organization_ids(cutoff: datetime):
    """Organizations with a live member whose character is held by an account that
    logged in since ``cutoff``: a current tenure on the character's roster entry."""
    return OrganizationMembership.objects.filter(
        left_at__isnull=True,
        exiled_at__isnull=True,
        **{
            f"{_PLAYED_TENURE}__end_date__isnull": True,
            f"{_PLAYED_TENURE}__player_data__account__last_login__gte": cutoff,
        },
    ).values("organization_id")


def mark_dormant_houses(*, now: datetime | None = None) -> int:
    """Stamp ``dormant_since`` on every awake organization that has income to accrue
    and no played character. One statement; returns the rows stamped."""
    moment = now if now is not None else timezone.now()
    cutoff = moment - timedelta(days=DominionConfig.load().dormancy_window_days)
    # Houses only: an organization with a family is one a player can app into and
    # inherit; an institution with none (a guild, a temple, the Crown's own office)
    # has no one to hoard for and keeps its books running.
    sleepers = (
        Organization.objects.filter(
            dormant_since__isnull=True, family__isnull=False, income_streams__isnull=False
        )
        .exclude(pk__in=_played_organization_ids(cutoff))
        .distinct()
    )
    pks = list(sleepers.values_list("pk", flat=True))
    if not pks:
        return 0
    count = Organization.objects.filter(pk__in=pks).update_with_reason(
        dormant_since=moment, reason="the weekly dormancy pass stamps houses nobody plays"
    )
    _flush(pks)
    return count


def wake_houses_for(account) -> int:
    """Clear ``dormant_since`` on every dormant organization a character held by
    ``account`` is a live member of: the login and roster-approval hook."""
    if account is None or not PlayerData.objects.filter(account=account).exists():
        return 0
    pks = list(
        Organization.objects.filter(
            dormant_since__isnull=False,
            memberships__left_at__isnull=True,
            memberships__exiled_at__isnull=True,
            **{
                f"memberships__{_PLAYED_TENURE}__end_date__isnull": True,
                f"memberships__{_PLAYED_TENURE}__player_data__account": account,
            },
        )
        .distinct()
        .values_list("pk", flat=True)
    )
    if not pks:
        return 0
    count = Organization.objects.filter(pk__in=pks).update_with_reason(
        dormant_since=None, reason="a member's player is back; the house wakes"
    )
    _flush(pks)
    return count


def _flush(pks: list[int]) -> None:
    """Drop the touched rows from the identity map so the next read sees the stamp."""
    for org in Organization.objects.filter(pk__in=pks):
        Organization.flush_cached_instance(org)
