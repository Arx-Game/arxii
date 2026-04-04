"""Service functions for the GameWeek system."""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from world.game_clock.models import GameSeason, GameWeek

logger = logging.getLogger("world.game_clock.weeks")


@transaction.atomic
def get_current_game_week() -> GameWeek:
    """Return the current GameWeek, creating one if none exists.

    If no GameWeek exists at all (fresh install), creates Season 1 and
    Week 1 starting now. Uses transaction.atomic to prevent duplicate
    bootstrap from concurrent requests.
    """
    current = GameWeek.get_current()
    if current is not None:
        return current

    # Bootstrap: create Season 1, Week 1
    # The unique_current_game_week constraint ensures only one concurrent
    # request can succeed; the loser gets IntegrityError and retries.
    logger.info("No current GameWeek found. Bootstrapping Season 1, Week 1.")
    season, _ = GameSeason.objects.get_or_create(number=1, defaults={"name": "Season 1"})
    try:
        return GameWeek.objects.create(
            number=1,
            season=season,
            started_at=timezone.now(),
            is_current=True,
        )
    except IntegrityError:
        # Another request bootstrapped first — return the one they created.
        return GameWeek.objects.get(is_current=True)


@transaction.atomic
def advance_game_week() -> GameWeek:
    """Close the current week and create the next one.

    Called by the weekly rollover cron. Closes the current week (sets
    ``ended_at`` and ``is_current=False``), then creates a new week with
    ``number + 1`` in the same season.

    Returns the newly created GameWeek.
    """
    now = timezone.now()
    # Lock the current week row to prevent concurrent advances.
    current = GameWeek.objects.select_for_update().filter(is_current=True).first()
    if current is None:
        current = get_current_game_week()
        # Re-fetch with lock after bootstrap.
        current = GameWeek.objects.select_for_update().get(pk=current.pk)

    # Close current week
    current.ended_at = now
    current.is_current = False
    current.save(update_fields=["ended_at", "is_current"])

    # Check if a new season was started (latest season differs from current week's).
    # If so, reset week number to 1. Otherwise increment.
    latest_season = GameSeason.objects.order_by("-number").first()
    if latest_season and latest_season != current.season:
        next_season = latest_season
        next_number = 1
    else:
        next_season = current.season
        next_number = current.number + 1

    new_week = GameWeek.objects.create(
        number=next_number,
        season=next_season,
        started_at=now,
        is_current=True,
    )

    logger.info(
        "Advanced to %s (closed %s)",
        new_week,
        current,
    )
    return new_week


def get_game_week_for_date(dt: timezone.datetime) -> GameWeek | None:
    """Find which GameWeek a real-world datetime falls within.

    Returns None if the date doesn't fall within any tracked week
    (e.g., during downtime gaps).
    """
    return (
        GameWeek.objects.filter(
            started_at__lte=dt,
        )
        .filter(
            # Either ended_at is after dt, or it's the current week (no end yet)
            models_q_ended_after_or_current(dt),
        )
        .order_by("-started_at")
        .first()
    )


def models_q_ended_after_or_current(dt: timezone.datetime) -> Q:
    """Q filter: ended_at > dt OR (ended_at IS NULL AND is_current)."""
    return Q(ended_at__gt=dt) | Q(ended_at__isnull=True, is_current=True)


def start_new_season(name: str = "") -> GameSeason:
    """Start a new season. The next advance_game_week will reset to Week 1.

    Creates the new GameSeason. On next advance, ``advance_game_week``
    detects that the latest season differs from the current week's season
    and resets the week number to 1.
    """
    last_season = GameSeason.objects.order_by("-number").first()
    next_number = (last_season.number + 1) if last_season else 1

    season = GameSeason.objects.create(number=next_number, name=name)

    # The next call to advance_game_week will detect the new season
    # (latest season != current week's season) and reset to Week 1.

    logger.info("Started %s", season)
    return season
