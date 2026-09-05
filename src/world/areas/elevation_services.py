"""Area elevation (#696 gap 3): a player-earned level increase, not a staff grant.

``EditAreaAction`` (``actions/definitions/world_builder.py``) stays the separate
warrant-gated staff/GM override that can set ``area.level`` directly. This module is
the parallel path a declarer without a build warrant walks instead: hold enough of the
area's BUILDING-level descendants (a proxy for meaningful stake in the place) and keep
its ORDER stat above the configured floor, then pay the coin cost. ``AreaElevationRequirement``
(``world/areas/models.py``) is the authored threshold table, one row per destination level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction

from world.areas.constants import AreaLevel
from world.areas.models import Area, AreaElevationRequirement
from world.locations.constants import HolderType, StatKey
from world.locations.services import area_stat_total, effective_owner_for_area

if TYPE_CHECKING:
    from world.currency.models import CharacterPurse, OrganizationTreasury
    from world.scenes.models import Persona

# Bounded BFS depth for the descendant walk — there are only 9 AreaLevel rungs, so a
# subtree can never be deeper than that; mirrors locations.services._AREA_ANCESTOR_WALK_CAP.
_AREA_DESCENDANT_WALK_CAP = len(AreaLevel.choices)


def next_level(area: Area) -> int | None:
    """The next ``AreaLevel`` value above ``area.level``, or ``None`` at the ceiling."""
    higher = [value for value in AreaLevel.values if value > area.level]
    return min(higher) if higher else None


def _declarer_holds_area(area: Area, *, declarer: Persona) -> bool:
    """Whether ``declarer`` is the effective owner's holder on ``area``.

    Either the row's holder is ``declarer``'s own persona, or the row's holder is an
    organization ``declarer`` can administer. "Can administer" reuses ``is_org_leader``
    (an active membership at an org-leadership rank) rather than
    ``houses.services.can_administer_domain`` — that helper also accepts the
    ``domain-steward`` office, but it takes a ``Domain`` instance, and a BUILDING-level
    area's effective owner need not be a ``Domain`` at all (any area can carry a
    ``LocationOwnership`` row). ``is_org_leader`` is the generic, Domain-free half of
    that predicate.
    """
    from world.societies.houses.services import is_org_leader  # noqa: PLC0415

    row = effective_owner_for_area(area)
    if row is None:
        return False
    if row.holder_type == HolderType.PERSONA:
        return row.holder_persona_id == declarer.pk
    return is_org_leader(declarer, row.holder_organization)


def _building_descendants(area: Area) -> list[Area]:
    """Every BUILDING-level area beneath ``area`` (BFS over ``children``, SQLite-safe).

    BUILDING is ``AreaLevel``'s floor, so a BUILDING area is always a leaf
    (``Area.clean()`` requires a strictly lower child level than its parent, and there
    is no level below BUILDING) — this returns every leaf building in the subtree, not
    just direct children. Walks ``parent``/``children`` FKs directly, deliberately not
    the ``AreaClosure`` materialized view, so it works identically on the SQLite fast
    tier — the same idiom as ``area_stat_total`` and ``effective_owner_for_area``.
    """
    result: list[Area] = []
    frontier = [area]
    seen = {area.pk}
    depth = 0
    while frontier and depth < _AREA_DESCENDANT_WALK_CAP:
        children = Area.objects.filter(parent_id__in=[a.pk for a in frontier])
        frontier = []
        for child in children:
            if child.pk in seen:
                continue
            seen.add(child.pk)
            if child.level == AreaLevel.BUILDING:
                result.append(child)
            else:
                frontier.append(child)
        depth += 1
    return result


def held_building_count(area: Area, *, declarer: Persona) -> int:
    """How many of ``area``'s BUILDING-level descendants ``declarer`` effectively holds."""
    return sum(
        1
        for building in _building_descendants(area)
        if _declarer_holds_area(building, declarer=declarer)
    )


@dataclass
class ElevationEligibility:
    """The result of checking a declarer's standing to elevate an area (#696 gap 3)."""

    eligible: bool
    held_buildings: int
    order_stat: int
    requirement: AreaElevationRequirement | None
    reasons: list[str] = field(default_factory=list)


def elevation_eligibility(area: Area, *, declarer: Persona) -> ElevationEligibility:
    """Check ``declarer``'s standing to elevate ``area`` to its next level.

    Reads are never mutating — safe to call for a read-only eligibility display; a
    real declaration re-checks inside ``declare_elevation``'s transaction.
    """
    target = next_level(area)
    held = held_building_count(area, declarer=declarer)
    order = area_stat_total(area, StatKey.ORDER)
    if target is None:
        return ElevationEligibility(
            eligible=False,
            held_buildings=held,
            order_stat=order,
            requirement=None,
            reasons=["This area is already at the highest level."],
        )
    requirement = AreaElevationRequirement.objects.filter(to_level=target).first()
    if requirement is None:
        return ElevationEligibility(
            eligible=False,
            held_buildings=held,
            order_stat=order,
            requirement=None,
            reasons=["No elevation requirement is configured for that level yet."],
        )
    reasons: list[str] = []
    if held < requirement.min_held_buildings:
        reasons.append(f"Hold {requirement.min_held_buildings} buildings here; you hold {held}.")
    if order < requirement.min_order_stat:
        reasons.append(
            f"This area's order must be at least {requirement.min_order_stat}; it is {order}."
        )
    return ElevationEligibility(
        eligible=not reasons,
        held_buildings=held,
        order_stat=order,
        requirement=requirement,
        reasons=reasons,
    )


def declare_elevation(
    area: Area,
    *,
    declarer: Persona,
    treasury_or_purse: CharacterPurse | OrganizationTreasury,
) -> Area:
    """Elevate ``area`` to its next level, charging the requirement's cost (#696 gap 3).

    Re-checks eligibility inside the transaction (no stale read between a player's
    confirm and the write), then sinks ``cost_coppers`` through ``transfer`` with no
    destination — a pure sink, mirroring ``items.market.services._pay``'s
    seller-is-None branch. Raises ``ValidationError`` (carrying the refusal reasons)
    when ineligible; propagates ``transfer``'s own ``ValidationError`` on insufficient
    funds.
    """
    from world.currency.models import OrganizationTreasury as _OrganizationTreasury  # noqa: PLC0415
    from world.currency.services import transfer  # noqa: PLC0415

    with transaction.atomic():
        eligibility = elevation_eligibility(area, declarer=declarer)
        requirement = eligibility.requirement
        if not eligibility.eligible or requirement is None:
            # eligible=True only when elevation_eligibility matched a requirement row,
            # but the None check keeps this branch's typing honest without an assert.
            raise ValidationError(eligibility.reasons or ["No elevation requirement matched."])
        reason = f"area elevation: {area.name} to {AreaLevel(requirement.to_level).label}"
        if requirement.cost_coppers > 0:
            kwargs: dict[str, Any] = (
                {"from_treasury": treasury_or_purse}
                if isinstance(treasury_or_purse, _OrganizationTreasury)
                else {"from_purse": treasury_or_purse}
            )
            transfer(amount=requirement.cost_coppers, reason=reason, **kwargs)
        area.level = requirement.to_level
        area.save(update_fields=["level"])
    return area
