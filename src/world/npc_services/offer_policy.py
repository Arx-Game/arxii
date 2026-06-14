"""POOL-draw count policy for mission offers (#726).

The unified offer machinery (``services.available_offers``) samples POOL-mode
offers down to a ``pool_count`` when one is supplied; historically the live
caller passed ``None`` (show every eligible offer), so the standing-driven count
the design called for never ran. This module owns the *how many*: it reads the
PC's durable standing with the NPC and maps it through the
``MISSION_POOL_COUNT_BANDS`` tiers so a stranger sees one trial job and a trusted
contact sees a full slate.

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
)
from world.npc_services.models import NPCStanding

if TYPE_CHECKING:
    from world.scenes.models import Persona


def mission_pool_count(*, persona: Persona, npc_persona: Persona | None) -> int:
    """POOL offer count to surface for ``persona`` at this NPC (#726).

    Class-1 nameless functionaries (``npc_persona is None``) and any PC with no
    ``NPCStanding`` row (or neutral/negative affection) get
    ``MISSION_POOL_COUNT_FLOOR`` — one trial job. Otherwise the count is the
    highest ``MISSION_POOL_COUNT_BANDS`` tier whose affection floor the standing
    meets. A single ``values_list`` read; no row → treated as affection 0.

    Org-standing as an additional input is a deferred follow-up; v1 keys on the
    per-NPC standing only.
    """
    affection = 0
    if npc_persona is not None:
        affection = (
            NPCStanding.objects.filter(persona=persona, npc_persona=npc_persona)
            .values_list("affection", flat=True)
            .first()
            or 0
        )
    count = MISSION_POOL_COUNT_FLOOR
    # Bands are ascending by floor; the last one whose floor is met wins.
    for floor, band_count in MISSION_POOL_COUNT_BANDS:
        if affection >= floor:
            count = band_count
    return count
