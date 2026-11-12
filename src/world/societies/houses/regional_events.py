"""Regional events (#5069 slice 4): a disaster over a region is one row the formula
and the map both read.

The maintainer's rulings (2026-11-11):

- A blight, a war, a famine is a ``RegionalEvent`` over an Area with a start and an
  end. While it is open, every county and barony under the area reads a cut capacity
  and its people fall toward it by the formula; when it closes, the people climb back
  by the same formula. Nothing ticks: the land beneath is rebased once at open and
  once at close, so the writes are bounded by the footprint.
- Dormancy freezes accumulators, never equilibria: a dormant house's land is struck
  and heals exactly like a played one. The per-house ``DomainCrisis`` is the
  player-facing half, spawned only for an awake house inside the footprint, so the
  house that is played has something to judge and the empty one takes the ambient
  hit silently.
- Staff open events by hand first; systemic spawners come later and write the same
  row.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from world.areas.models import Area
from world.areas.services import area_subtree_pks
from world.societies.houses.constants import CrisisOrigin
from world.societies.houses.models import Domain, RegionalEvent, RegionalEventKind


def active_events(*, now: datetime | None = None):
    """Events open at ``now``: started and not yet ended."""
    moment = now if now is not None else timezone.now()
    open_rows = RegionalEvent.objects.filter(started_at__lte=moment, ended_at__isnull=True)
    return open_rows.select_related("kind", "area")


def active_capacity_multipliers(*, now: datetime | None = None) -> dict[int, float]:
    """For every Area under an open event, the fraction of its capacity the land can
    still feed: the product over events of ``1 - cut * severity``. Areas under no
    event are absent (read as 1.0). One query for the events and one subtree read per
    event; events are few."""
    multipliers: dict[int, float] = {}
    for event in active_events(now=now):
        factor = 1 - (event.kind.capacity_cut_pct * event.severity_pct) / 10_000
        for area_pk in area_subtree_pks(event.area):
            multipliers[area_pk] = multipliers.get(area_pk, 1.0) * factor
    return multipliers


def _footprint_domains(area: Area) -> list[Domain]:
    """Every holding under ``area``, the area's own included."""
    return list(
        Domain.objects.filter(pk__in=area_subtree_pks(area)).select_related("owner_org", "area")
    )


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _rebase_all(domains: Iterable[Domain], *, at: datetime, prosperity: int, unrest: int) -> None:
    """Record each holding's people as of ``at`` and move its prosperity and unrest by
    the deltas given, in one pass over the footprint."""
    from world.societies.houses.demography import populations_now  # noqa: PLC0415

    domains = list(domains)
    figures = populations_now(domains, at=at)
    for domain in domains:
        domain.population = figures[domain.pk]
        domain.population_rebased_at = at
        domain.prosperity = _clamp(domain.prosperity + prosperity)
        domain.unrest = _clamp(domain.unrest + unrest)
        domain.save(update_fields=["population", "population_rebased_at", "prosperity", "unrest"])


@transaction.atomic
def open_regional_event(  # noqa: PLR0913 - a disaster is a kind, a place, a strength, a note and who
    *,
    kind: RegionalEventKind,
    area: Area,
    severity_pct: int = 100,
    note: str = "",
    opened_by=None,
    now: datetime | None = None,
) -> RegionalEvent:
    """Open ``kind`` over ``area``: rebase the land beneath to this moment (so the cut
    starts from today's people, not a rewritten past), land the kind's prosperity and
    unrest deltas, record the event, and give every awake house holding land inside a
    crisis of the kind's type to judge."""
    from world.societies.houses.crisis_services import open_crisis  # noqa: PLC0415

    moment = now if now is not None else timezone.now()
    domains = _footprint_domains(area)
    # Rebased before the row exists: the formula reads no cut yet, so the base is the
    # figure the land had the moment the event struck.
    _rebase_all(domains, at=moment, prosperity=kind.prosperity_delta, unrest=kind.unrest_delta)
    event = RegionalEvent.objects.create(
        kind=kind,
        area=area,
        severity_pct=severity_pct,
        started_at=moment,
        opened_by=opened_by,
        note=note,
    )
    if kind.crisis_type_id is not None:
        for domain in _highest_holding_per_awake_house(domains):
            open_crisis(
                domain=domain,
                origin=CrisisOrigin.REGIONAL,
                crisis_type=kind.crisis_type,
                description=kind.description,
            )
    return event


def _highest_holding_per_awake_house(domains: Iterable[Domain]) -> list[Domain]:
    """One holding per awake house: the county over its chain barony, so a duke
    struck across both reads one crisis, not one per rung. Dormant and unclaimed
    land takes the ambient hit with nothing to judge."""
    chosen: dict[int, Domain] = {}
    for domain in domains:
        owner = domain.owner_org
        if owner is None or owner.dormant_since is not None:
            continue
        held = chosen.get(owner.pk)
        if held is None or domain.area.level < held.area.level:
            chosen[owner.pk] = domain
    return list(chosen.values())


@transaction.atomic
def close_regional_event(event: RegionalEvent, *, now: datetime | None = None) -> RegionalEvent:
    """Close ``event``: rebase the land beneath to the figure the cut left it at, take the
    kind's deltas back off, and end the row; from here the people climb back by formula."""
    moment = now if now is not None else timezone.now()
    domains = _footprint_domains(event.area)
    # Rebased while the row is still open: the formula still reads the cut, so the base
    # is the hurt figure, and recovery starts from it.
    _rebase_all(
        domains, at=moment, prosperity=-event.kind.prosperity_delta, unrest=-event.kind.unrest_delta
    )
    event.ended_at = moment
    event.save(update_fields=["ended_at"])
    return event
