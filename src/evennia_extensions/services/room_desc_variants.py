"""Resolve the season/phase-appropriate description variant for a room (#3291)."""

from __future__ import annotations

from datetime import datetime

from evennia_extensions.models import RoomDescVariant, RoomProfile


def resolve_room_description(profile: RoomProfile, ic_now: datetime | None) -> str | None:
    """Return the most specific authored variant's text for ``ic_now``, or ``None``.

    Most-specific-wins: (season, phase) > (season, None) > (None, phase). ``None``
    means "no variant applies"; the caller keeps whatever base description it
    already has. ``ic_now`` is ``None`` when the game clock has never been set
    (e.g. pre-launch); that always resolves to ``None`` with no error, per #3291
    Decision 2.
    """
    if ic_now is None:
        return None

    from world.game_clock.services import (  # noqa: PLC0415
        phase_from_ic_time,
        season_from_ic_time,
    )

    season = season_from_ic_time(ic_now)
    phase = phase_from_ic_time(ic_now)

    variants = {
        (variant.season, variant.phase): variant.description
        for variant in RoomDescVariant.objects.filter(room_profile=profile)
    }

    for key in ((season, phase), (season, None), (None, phase)):
        if key in variants:
            return variants[key]
    return None
