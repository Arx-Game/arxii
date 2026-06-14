"""POOL-draw count policy for mission offers (#726, #1020).

The unified offer machinery (``services.available_offers``) samples POOL-mode
offers down to a ``pool_count`` when one is supplied; historically the live
caller passed ``None`` (show every eligible offer), so the standing-driven count
the design called for never ran. This module owns the *how many*: it reads the
PC's durable standing and maps it through count bands so a stranger sees one
trial job and a trusted contact sees a full slate.

Two standing inputs (#1020): the per-NPC ``NPCStanding.affection`` and — when
the role fronts an organization (``NPCRole.faction_affiliation``) — the
persona's ``OrganizationReputation`` tier with that org. The final count is the
``max`` of the two, so org favor lifts the slate from *any* of that org's
functionaries even with no personal standing, while a personally-cultivated
contact still lifts it on their own.

Deliberately narrow. *Which* missions and *what tier* stay in the predicate
system (an offer's ``eligibility_rule`` — ``min_npc_standing``,
``min_org_reputation``, ``has_completed_mission``, …). Chain / high-stakes
emphasis stays in ``MissionOfferDetails.draw_priority`` (the draw, not the
count). This module computes a single integer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.npc_services.constants import (
    MISSION_POOL_COUNT_BANDS,
    MISSION_POOL_COUNT_FLOOR,
    MISSION_POOL_ORG_COUNT_BANDS,
)
from world.npc_services.models import NPCStanding
from world.societies.models import OrganizationReputation
from world.societies.types import ReputationTier

if TYPE_CHECKING:
    from world.npc_services.models import NPCRole
    from world.scenes.models import Persona

# Tier → rank from the source enum's declaration order (reviled=0 … revered=8).
# Derived, not duplicated, so a new tier in ``societies.types`` flows through.
_TIER_RANK: dict[ReputationTier, int] = {tier: rank for rank, tier in enumerate(ReputationTier)}


def mission_pool_count(*, role: NPCRole, persona: Persona, npc_persona: Persona | None) -> int:
    """POOL offer count to surface for ``persona`` at this NPC (#726, #1020).

    ``max`` of the per-NPC standing count and the org-reputation count (the
    latter only when ``role`` fronts an org). Each input falls back to
    ``MISSION_POOL_COUNT_FLOOR`` (one trial job) when absent, so the ``max`` is a
    no-op for strangers / non-affiliated roles and behavior matches #726.
    """
    return max(
        _npc_standing_count(persona, npc_persona),
        _org_reputation_count(role, persona),
    )


def _band_count(bands: tuple[tuple[int, int], ...], value: int) -> int:
    """Walk ascending ``(floor, count)`` bands; the highest met floor wins."""
    count = MISSION_POOL_COUNT_FLOOR
    for floor, band_count in bands:
        if value >= floor:
            count = band_count
    return count


def _npc_standing_count(persona: Persona, npc_persona: Persona | None) -> int:
    """Count from per-NPC ``NPCStanding.affection`` (#726).

    Class-1 functionaries (``npc_persona is None``) and any PC with no standing
    row (or neutral/negative affection) land on the floor. One ``values_list``
    read; no row → affection 0.
    """
    affection = 0
    if npc_persona is not None:
        affection = (
            NPCStanding.objects.filter(persona=persona, npc_persona=npc_persona)
            .values_list("affection", flat=True)
            .first()
            or 0
        )
    return _band_count(MISSION_POOL_COUNT_BANDS, affection)


def _org_reputation_count(role: NPCRole, persona: Persona) -> int:
    """Count from the persona's org reputation, when ``role`` fronts an org (#1020).

    No affiliation or no reputation row → floor (the ``max`` in
    ``mission_pool_count`` then leaves the NPC-standing count untouched). One
    indexed read, only when the role fronts an org.
    """
    org_id = role.faction_affiliation_id
    if org_id is None:
        return MISSION_POOL_COUNT_FLOOR
    value = (
        OrganizationReputation.objects.filter(persona=persona, organization_id=org_id)
        .values_list("value", flat=True)
        .first()
    )
    if value is None:
        return MISSION_POOL_COUNT_FLOOR
    tier_rank = _TIER_RANK[ReputationTier.from_value(value)]
    return _band_count(MISSION_POOL_ORG_COUNT_BANDS, tier_rank)
