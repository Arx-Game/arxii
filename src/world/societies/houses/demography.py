"""Demography of the noble layer (#5069 slice 1): population as a formula, capacity
from terrain, terrain counts written where footprints change.

The maintainer's rulings (2026-11-10/11):

- A barony is one pip; a county is its baronies plus a hinterland whose people are
  an undistributed rural pool. Importance is population, never pip count.
- Population never ticks. ``population_now`` is arithmetic over the base a Domain
  last recorded, its capacity, the rate and the in-character months since; a write
  happens only on a rebase (a regional event, a staff edit, layout). Dormancy freezes
  coin, never this: the land keeps running whether or not anyone plays it.
- Pips and terrain never tick either. A holding's terrain mix is counted when its
  footprint changes and cached on ``DomainTerrainCount``; capacity is the counts times
  the authored ``TerrainCalibration``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime
import math

from django.db import transaction
from django.utils import timezone

from world.areas.constants import AreaLevel
from world.areas.models import Area
from world.areas.worldmap.models import AreaFootprintPip, TerrainPip
from world.societies.houses.models import (
    Domain,
    DomainTerrainCount,
    DominionConfig,
    TerrainCalibration,
)
from world.societies.houses.regional_events import active_capacity_multipliers

IC_DAYS_PER_MONTH = 30
_SECONDS_PER_IC_MONTH = IC_DAYS_PER_MONTH * 24 * 60 * 60


def ic_months_between(start: datetime, end: datetime) -> float:
    """In-character months from ``start`` to ``end`` (real datetimes). Zero when no
    game clock exists: with no clock no in-character time passes."""
    from world.game_clock.services import get_ic_date_for_real_time  # noqa: PLC0415

    ic_start = get_ic_date_for_real_time(start)
    ic_end = get_ic_date_for_real_time(end)
    if ic_start is None or ic_end is None:
        return 0.0
    return max(0.0, (ic_end - ic_start).total_seconds() / _SECONDS_PER_IC_MONTH)


def population_now(domain: Domain, *, at: datetime | None = None) -> int:
    """The holding's people at ``at`` (now by default), moved from the recorded base
    toward capacity by the elapsed in-character months. Reads only.

    The gap closes exponentially: each month ``rate`` percent of what remains between
    the people and the capacity goes away, in either direction, so a holding above its
    capacity shrinks toward it by the same curve a holding below grows.
    """
    return populations_now([domain], at=at)[domain.pk]


def populations_now(domains: Iterable[Domain], *, at: datetime | None = None) -> dict[int, int]:
    """``population_now`` for many holdings with one clock read and one dials read:
    the realm graph calls this once per realm, never the single form per row."""
    from world.game_clock.models import GameClock  # noqa: PLC0415

    moment = at if at is not None else timezone.now()
    clock = GameClock.get_active()
    rate = DominionConfig.load().population_rate_pct_per_month / 100
    # A regional event over the land cuts the capacity the people fall toward; the
    # row is the only state, so every read sees the same cut (#5069 slice 4).
    multipliers = active_capacity_multipliers(now=moment)
    figures: dict[int, int] = {}
    for domain in domains:
        months = 0.0
        if clock is not None:
            ic_then = clock.get_ic_now(real_now=domain.population_rebased_at)
            ic_now = clock.get_ic_now(real_now=moment)
            months = max(0.0, (ic_now - ic_then).total_seconds() / _SECONDS_PER_IC_MONTH)
        if months <= 0:
            figures[domain.pk] = domain.population
            continue
        capacity = domain.population_capacity * multipliers.get(domain.area_id, 1.0)
        gap = capacity - domain.population
        figures[domain.pk] = max(0, round(capacity - gap * math.exp(-rate * months)))
    return figures


def rebase_population(domain: Domain, *, at: datetime | None = None) -> Domain:
    """Record the current figure as the new base, so a change to capacity or an
    event's cut starts from today rather than rewriting the past."""
    moment = at if at is not None else timezone.now()
    domain.population = population_now(domain, at=moment)
    domain.population_rebased_at = moment
    domain.save(update_fields=["population", "population_rebased_at"])
    return domain


def terrain_counts_for(area: Area) -> dict[str, int]:
    """How many of ``area``'s own footprint pips are each terrain. A footprint row
    names its lowest holder (ADR-0328), so a county's own pips exclude its baronies'."""
    coords = set(AreaFootprintPip.objects.filter(area=area).values_list("x", "y"))
    if not coords:
        return {}
    xs = [x for x, _ in coords]
    ys = [y for _, y in coords]
    # The terrain table is the whole world; a bounding box keeps the fetch to the
    # holding's neighbourhood and the set intersection does the exact join.
    rows = TerrainPip.objects.filter(
        x__gte=min(xs), x__lte=max(xs), y__gte=min(ys), y__lte=max(ys)
    ).values_list("x", "y", "terrain")
    return dict(Counter(terrain for x, y, terrain in rows if (x, y) in coords))


def capacity_from(counts: dict[str, int], *, level: int) -> int:
    """People the counted ground can feed: pips times the terrain's calibration, times
    the barony factor on a barony (a seat holds a town on a farm's worth of ground).
    A terrain with no calibration row feeds nobody."""
    per_pip = {row.terrain: row.capacity_per_pip for row in TerrainCalibration.objects.all()}
    total = sum(pips * per_pip.get(terrain, 0) for terrain, pips in counts.items())
    if level == AreaLevel.BARONY:
        total *= DominionConfig.load().barony_capacity_factor
    return total


@transaction.atomic
def refresh_terrain_counts(area: Area) -> int:
    """Recount ``area``'s terrain and recompute its Domain's capacity. Returns the
    capacity, or 0 for an area with no Domain (a duchy, a region, open ground)."""
    domain = Domain.objects.filter(pk=area.pk).first()
    if domain is None:
        return 0
    counts = terrain_counts_for(area)
    DomainTerrainCount.objects.filter(domain=domain).delete()
    DomainTerrainCount.objects.bulk_create(
        [
            DomainTerrainCount(domain=domain, terrain=terrain, pips=pips)
            for terrain, pips in counts.items()
        ]
    )
    # A staff figure stands in for the terrain's (a capital and a fort on the same ground).
    if domain.capacity_override is not None:
        domain.population_capacity = domain.capacity_override
    else:
        domain.population_capacity = capacity_from(counts, level=area.level)
    domain.save(update_fields=["population_capacity"])
    return domain.population_capacity


def set_capacity_override(domain: Domain, capacity: int | None) -> Domain:
    """Set (or clear, with ``None``) the staff figure a holding's capacity reads instead
    of its terrain, rebasing first so the curve starts from today's people."""
    rebase_population(domain)
    domain.capacity_override = capacity
    domain.save(update_fields=["capacity_override"])
    refresh_terrain_counts(domain.area)
    return domain


def prosperity_modifier_for(domain: Domain) -> int:
    """The terrain's pull on a laid-out holding's prosperity: each calibration's
    modifier weighted by the share of the holding's pips that terrain is, rounded."""
    counts = dict(domain.terrain_counts.values_list("terrain", "pips"))
    total = sum(counts.values())
    if total == 0:
        return 0
    modifiers = {row.terrain: row.prosperity_modifier for row in TerrainCalibration.objects.all()}
    weighted = sum(pips * modifiers.get(terrain, 0) for terrain, pips in counts.items())
    return round(weighted / total)


def refresh_terrain_counts_for(areas: Iterable[Area]) -> int:
    """``refresh_terrain_counts`` over every distinct area given; returns how many had
    a Domain to update."""
    done = 0
    seen: set[int] = set()
    for area in areas:
        if area.pk in seen:
            continue
        seen.add(area.pk)
        if Domain.objects.filter(pk=area.pk).exists():
            refresh_terrain_counts(area)
            done += 1
    return done
