"""Player-driven legend spreading services (#745 — Spread a Tale).

`get_spreadable_deeds` powers the deed picker; the value formula + resolver
(added in later tasks) turn a scene-action check outcome into a `spread_deed`
call.
"""

from __future__ import annotations

from django.db.models import QuerySet

from world.societies.models import LegendEntry, OrganizationMembership

SPREAD_TALE_ACTION_KEY = "spread_a_tale"

# success_level -> fraction of base_value (failure / <=0 yields 0). Tunable.
TIER_PAYOFF: dict[int, float] = {0: 0.0, 1: 0.10, 2: 0.30, 3: 0.60, 4: 1.00}


def compute_spread_value(*, base_value: int, success_level: int, multiplier: float) -> int:
    """Legend value a single telling adds, before the per-deed cap clamp.

    ``base × tier_payoff(success_level) × traffic_multiplier``. Failures (or
    success_level <= 0) add nothing. success_level above the table tops out at
    the max payoff fraction.
    """
    if success_level <= 0:
        return 0
    payoff = TIER_PAYOFF.get(success_level, max(TIER_PAYOFF.values()))
    return round(base_value * payoff * multiplier)


def get_spreadable_deeds(persona) -> QuerySet[LegendEntry]:
    """Active deeds whose ``societies_aware`` intersects the persona's societies.

    A persona may spread tales known to any society they hold membership in
    (via an organization in that society). Inactive deeds and deeds no society
    of theirs knows of are excluded.
    """
    society_ids = OrganizationMembership.objects.filter(persona=persona).values_list(
        "organization__society_id", flat=True
    )
    return (
        LegendEntry.objects.filter(is_active=True, societies_aware__in=society_ids)
        .distinct()
        .order_by("-created_at")
    )
