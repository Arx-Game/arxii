"""Levies: every controller above a business takes its cut (#4060 slice 3).

Maintainer ruling (2026-09-28): a business under both a Lord Mayor's tax and a
gang's protection money pays both; it is never either/or. A ``Levy`` names a
rung (an Area, or an outdoor room for a crew) and a rate; whoever controls that
rung right now takes it (the Domain's owner for TAX, the Turf's holder for
PROTECTION), so the take follows control the way kick-up does. A controller
never levies its own holdings. The takes come off a holding stream's gross at
accrual, before it pools for the owner, and each pools in the levy's own LEVY
stream, collected like any other (ADR-0081). Together they never exceed the
gross: over 100 percent, each take scales down proportionally.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.areas.models import Area
    from world.currency.models import OrgIncomeStream
    from world.societies.models import Levy

logger = logging.getLogger(__name__)

_CHAIN_CAP = 10  # defensive bound on the parent walk; area trees are shallow
LEVY_RATE_MAX = 100


def _site_lookup(site: Area | RoomProfile) -> dict:
    from world.areas.models import Area  # noqa: PLC0415

    if isinstance(site, Area):
        return {"area": site, "room_profile": None}
    return {"area": None, "room_profile": site}


def set_levy(site: Area | RoomProfile, kind: str, rate_pct: int) -> Levy:
    """Set (or switch off, at 0) the ``kind`` levy on ``site``."""
    from world.societies.models import Levy  # noqa: PLC0415

    if not 0 <= rate_pct <= LEVY_RATE_MAX:
        msg = "A levy takes between 0 and 100 percent."
        raise ValueError(msg)
    levy, _created = Levy.objects.get_or_create(kind=kind, **_site_lookup(site))
    levy.rate_pct = rate_pct
    levy.active = rate_pct > 0
    levy.full_clean()
    levy.save(update_fields=["rate_pct", "active", "updated_at"])
    ensure_levy_stream(levy)
    return levy


def _area_chain(area: Area | None) -> list[Area]:
    chain: list[Area] = []
    node = area
    while node is not None and len(chain) < _CHAIN_CAP:
        chain.append(node)
        node = node.parent
    return chain


def levies_over(*, area: Area | None, room_profile: RoomProfile | None = None) -> list[Levy]:
    """The active levies a business at this spot is under: its room's, then every rung up."""
    from world.societies.models import Levy  # noqa: PLC0415

    found: list[Levy] = []
    if room_profile is not None:
        found.extend(Levy.objects.filter(room_profile=room_profile, active=True))
    chain = _area_chain(area)
    if chain:
        by_area: dict[int, list[Levy]] = {}
        for levy in Levy.objects.filter(area__in=chain, active=True).select_related("area"):
            by_area.setdefault(levy.area_id, []).append(levy)
        for node in chain:
            found.extend(by_area.get(node.pk, []))
    return found


def ensure_levy_stream(levy: Levy) -> OrgIncomeStream | None:
    """The levy's LEVY stream on the rung's current controller; none while contested."""
    from world.currency.constants import IncomeStreamKind  # noqa: PLC0415
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415

    controller = levy.controller
    if controller is None:
        return levy.income_stream
    stream = levy.income_stream
    if stream is None:
        stream = OrgIncomeStream.objects.create(
            organization=controller,
            name=f"{levy.site_name}: {levy.get_kind_display().lower()}"[:100],
            kind=IncomeStreamKind.LEVY,
            gross_amount=0,
            area=levy.area,
            room_profile=levy.room_profile,
        )
        levy.income_stream = stream
        levy.save(update_fields=["income_stream"])
    elif stream.organization_id != controller.pk:
        stream.organization = controller
        stream.save(update_fields=["organization"])
    return stream


def ensure_levy_streams() -> int:
    """Weekly: every active levy has its stream on the current controller; the cycle's
    display total starts at zero (the payers' accruals rebuild it)."""
    from world.currency.constants import IncomeStreamKind  # noqa: PLC0415
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415
    from world.societies.models import Levy  # noqa: PLC0415

    count = 0
    for levy in Levy.objects.filter(active=True).select_related(
        "area", "room_profile", "income_stream"
    ):
        ensure_levy_stream(levy)
        count += 1
    for stream in OrgIncomeStream.objects.filter(kind=IncomeStreamKind.LEVY, gross_amount__gt=0):
        stream.gross_amount = 0
        stream.save(update_fields=["gross_amount"])
    return count


def apply_levies(payer: OrgIncomeStream, gross: int) -> int:
    """Take every applicable levy off ``gross`` into its controller's pool; return the rest.

    Only a holding's stream pays (a business); a rung's own base territory
    stream never does. A levy whose rung is contested, or whose controller is
    the payer itself, takes nothing.
    """
    holding = payer.domain_holding_or_none
    if holding is None or gross <= 0:
        return gross
    if holding.room_profile_id is not None:
        area = holding.room_profile.area
    elif holding.building_id is not None:
        area = holding.building.area
    else:
        area = holding.domain.area
    takes: list[tuple[Levy, int]] = []
    for levy in levies_over(area=area, room_profile=holding.room_profile):
        controller = levy.controller
        if controller is None or controller.pk == payer.organization_id:
            continue
        take = gross * levy.rate_pct // 100
        if take > 0:
            takes.append((levy, take))
    total = sum(take for _levy, take in takes)
    if total > gross:
        takes = [(levy, take * gross // total) for levy, take in takes]
        total = sum(take for _levy, take in takes)
    for levy, take in takes:
        stream = ensure_levy_stream(levy)
        if stream is None:  # pragma: no cover - controller checked above
            continue
        stream.uncollected_pool = stream.uncollected_pool + take
        stream.gross_amount = stream.gross_amount + take
        stream.save(update_fields=["uncollected_pool", "gross_amount"])
    return gross - total
