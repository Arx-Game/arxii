"""Renown system services (#676 Phase A).

Houses the fame-tier derivation, the persona-fame decay function, and the
organization-prestige decay function. Subsequent phases extend this module
with: renown event firing (Phase B), org-inflow + persona-outflow plumbing
(Phase C), source-prestige-recompute helpers for dwellings/items (Phases D/F).

The cron-driven decay sweep lives in ``world.societies.tasks`` and calls
the per-row decay functions defined here.
"""

from __future__ import annotations

import logging

from django.db import transaction

from world.scenes.models import Persona
from world.societies.constants import (
    FAME_DECAY_FLAT,
    FAME_DECAY_PCT,
    FAME_TIER_MULTIPLIERS,
    FAME_TIER_ORDER,
    FAME_TIER_THRESHOLDS,
    ORG_FAME_DECAY_FLAT,
    ORG_FAME_DECAY_PCT,
    ORG_PRESTIGE_DECAY_FLAT,
    ORG_PRESTIGE_DECAY_PCT,
    FameTier,
)
from world.societies.models import Organization

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fame tier derivation
# ---------------------------------------------------------------------------


def derive_fame_tier(fame_points: int) -> str:
    """Return the highest fame-tier name whose threshold is ≤ ``fame_points``.

    Walks ``FAME_TIER_ORDER`` from highest threshold down; first match wins.
    Returns the bare string value (``FameTier.NORMAL.value`` etc.) so callers
    can assign directly to ``persona.fame_tier`` without wrapping.
    """
    for tier_name in reversed(FAME_TIER_ORDER):
        if fame_points >= FAME_TIER_THRESHOLDS[tier_name]:
            return tier_name
    return FameTier.NORMAL.value


def fame_multiplier_for(fame_tier: str) -> float:
    """Look up the prestige-display multiplier for a fame tier."""
    return FAME_TIER_MULTIPLIERS[fame_tier]


def set_persona_fame(persona: Persona, new_fame_points: int) -> bool:
    """Write a new ``fame_points`` value and recompute ``fame_tier``.

    Returns True iff ``fame_tier`` changed (callers can hook tier-change
    notifications). ``new_fame_points`` is floored at 0 — fame is a
    non-negative buffer; negative buzz is captured via Reputation, not Fame.
    """
    floored = max(0, new_fame_points)
    new_tier = derive_fame_tier(floored)
    tier_changed = new_tier != persona.fame_tier
    persona.fame_points = floored
    persona.fame_tier = new_tier
    persona.save(update_fields=["fame_points", "fame_tier"])
    return tier_changed


# ---------------------------------------------------------------------------
# Fame decay (per-row primitive)
#
# Formula: new = max(0, old - FLAT - PCT * old)
#
# Per IC day cadence (cron interval in tasks.py is 8 real hours, matching
# the canonical 3:1 IC:OOC time ratio). The percentage term dominates at
# high fame; the flat term drains the residue at low fame.
# ---------------------------------------------------------------------------


def apply_persona_fame_decay(persona: Persona) -> bool:
    """Apply one tick of fame decay to ``persona``. Returns True iff tier changed.

    No-op for personas at ``fame_points == 0``.
    """
    if persona.fame_points <= 0:
        return False
    decayed = persona.fame_points - FAME_DECAY_FLAT - int(persona.fame_points * FAME_DECAY_PCT)
    return set_persona_fame(persona, decayed)


# ---------------------------------------------------------------------------
# Org accumulated-value decay
#
# accumulated_prestige and accumulated_fame decay each tick. accumulated_legend
# on covenants is permanent — NEVER touched by this function.
# ---------------------------------------------------------------------------


def apply_org_accumulated_decay(org: Organization) -> tuple[int, int]:
    """Apply one tick of decay to org accumulated_prestige + accumulated_fame.

    Returns a tuple of (new_accumulated_prestige, new_accumulated_fame).
    Floors at 0. Does NOT touch ``base_prestige`` (permanent) or
    ``accumulated_legend`` (permanent, covenant-only).
    """
    update_fields: list[str] = []
    new_prestige = org.accumulated_prestige
    if new_prestige > 0:
        new_prestige = max(
            0,
            new_prestige - ORG_PRESTIGE_DECAY_FLAT - int(new_prestige * ORG_PRESTIGE_DECAY_PCT),
        )
        if new_prestige != org.accumulated_prestige:
            org.accumulated_prestige = new_prestige
            update_fields.append("accumulated_prestige")
    new_fame = org.accumulated_fame
    if new_fame > 0:
        new_fame = max(
            0,
            new_fame - ORG_FAME_DECAY_FLAT - int(new_fame * ORG_FAME_DECAY_PCT),
        )
        if new_fame != org.accumulated_fame:
            org.accumulated_fame = new_fame
            update_fields.append("accumulated_fame")
    if update_fields:
        org.save(update_fields=update_fields)
    return new_prestige, new_fame


# ---------------------------------------------------------------------------
# Cron sweep entrypoints (called by world.societies.tasks)
# ---------------------------------------------------------------------------


@transaction.atomic
def decay_all_persona_fame() -> int:
    """Apply fame decay to every persona with positive fame. Returns count touched.

    Single transaction so a mid-sweep failure doesn't half-apply. Iterates
    only personas with ``fame_points > 0`` — avoids the no-op walk for the
    vast majority of personas at default state.
    """
    touched = 0
    for persona in Persona.objects.filter(fame_points__gt=0).iterator():
        apply_persona_fame_decay(persona)
        touched += 1
    logger.info("renown.fame_decay: applied to %d personas", touched)
    return touched


@transaction.atomic
def decay_all_org_accumulated() -> int:
    """Apply accumulated-prestige + accumulated-fame decay to every org with positive accumulation.

    Single transaction. Iterates only orgs with either accumulated value > 0.
    Does NOT touch covenants' accumulated_legend.
    """
    from django.db.models import Q  # noqa: PLC0415

    touched = 0
    for org in Organization.objects.filter(
        Q(accumulated_prestige__gt=0) | Q(accumulated_fame__gt=0)
    ).iterator():
        apply_org_accumulated_decay(org)
        touched += 1
    logger.info("renown.org_accumulated_decay: applied to %d organizations", touched)
    return touched
