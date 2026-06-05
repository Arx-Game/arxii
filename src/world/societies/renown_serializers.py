"""#676 Phase G — Renown REST API serializers.

Read-only view of a persona's renown:

* Four prestige axes (dwellings, items, orgs, deeds) + total + fame
  buffer + fame tier.
* Per-society reputation tiers (named labels, not numeric values).
* Recent deeds (LegendEntry rows) — title + base_value + created date.

Frontend renown tab consumes these via the
``PersonaViewSet.renown`` action. The structure is intentionally flat
and read-only — writes happen through the existing event-firing
services (fire_renown_award etc.), not through this API.
"""

from __future__ import annotations

from rest_framework import serializers

from world.scenes.models import Persona
from world.societies.constants import (
    FAME_TIER_MULTIPLIERS,
    FAME_TIER_THRESHOLDS,
    FameTier,
)
from world.societies.models import LegendEntry, SocietyReputation
from world.societies.types import ReputationTier


class _PrestigeBreakdownSerializer(serializers.Serializer):
    """Four-axis breakdown of the persona's total_prestige."""

    dwellings = serializers.IntegerField()
    items = serializers.IntegerField()
    orgs = serializers.IntegerField()
    deeds = serializers.IntegerField()
    total = serializers.IntegerField()


class _FameSerializer(serializers.Serializer):
    """Persona's fame state for the renown tab header."""

    points = serializers.IntegerField()
    tier = serializers.CharField()
    tier_label = serializers.CharField()
    tier_multiplier = serializers.FloatField()
    next_tier = serializers.CharField(allow_null=True)
    next_tier_threshold = serializers.IntegerField(allow_null=True)


class _SocietyReputationSerializer(serializers.Serializer):
    """One reputation entry: society + tier label (no raw number)."""

    society_id = serializers.IntegerField()
    society_name = serializers.CharField()
    tier = serializers.CharField()


class _DeedSerializer(serializers.Serializer):
    """LegendEntry summary for the recent-deeds list."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    base_value = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class RenownSerializer(serializers.Serializer):
    """Full renown payload for a single persona.

    Read-only. Writes happen through the event-firing services.
    """

    persona_id = serializers.IntegerField()
    persona_name = serializers.CharField()
    prestige = _PrestigeBreakdownSerializer()
    fame = _FameSerializer()
    reputation = _SocietyReputationSerializer(many=True)
    recent_deeds = _DeedSerializer(many=True)


def build_renown_payload(persona: Persona, *, deeds_limit: int = 20) -> dict:
    """Assemble the renown payload for ``persona``.

    Single function call; no caching layer (the underlying fields are
    denormalized on the persona row + a small N for reputation rows).
    Caller can cap deeds with ``deeds_limit``.
    """
    return {
        "persona_id": persona.pk,
        "persona_name": persona.name,
        "prestige": _build_prestige(persona),
        "fame": _build_fame(persona),
        "reputation": _build_reputation(persona),
        "recent_deeds": _build_recent_deeds(persona, limit=deeds_limit),
    }


def _build_prestige(persona: Persona) -> dict:
    return {
        "dwellings": persona.prestige_from_dwellings,
        "items": persona.prestige_from_items,
        "orgs": persona.prestige_from_orgs,
        "deeds": persona.prestige_from_deeds,
        "total": persona.total_prestige,
    }


def _build_fame(persona: Persona) -> dict:
    tier = persona.fame_tier
    next_tier_name, next_threshold = _next_tier_after(tier)
    return {
        "points": persona.fame_points,
        "tier": tier,
        "tier_label": FameTier(tier).label,
        "tier_multiplier": FAME_TIER_MULTIPLIERS[tier],
        "next_tier": next_tier_name,
        "next_tier_threshold": next_threshold,
    }


def _next_tier_after(current_tier: str) -> tuple[str | None, int | None]:
    """Return (next_tier_name, next_tier_threshold) for the tier above ``current_tier``.

    Returns (None, None) when already at the top tier.
    """
    tiers_in_order = list(FAME_TIER_THRESHOLDS.items())
    current_threshold = FAME_TIER_THRESHOLDS[current_tier]
    for name, threshold in tiers_in_order:
        if threshold > current_threshold:
            return name, threshold
    return None, None


def _build_reputation(persona: Persona) -> list[dict]:
    if not persona.is_established_or_primary:
        return []
    rows = (
        SocietyReputation.objects.filter(persona=persona)
        .select_related("society")
        .order_by("society__name")
    )
    return [
        {
            "society_id": row.society_id,
            "society_name": row.society.name,
            "tier": ReputationTier.from_value(row.value).value,
        }
        for row in rows
    ]


def _build_recent_deeds(persona: Persona, *, limit: int) -> list[dict]:
    deeds = LegendEntry.objects.filter(persona=persona).order_by("-created_at")[:limit]
    return [
        {
            "id": deed.pk,
            "title": deed.title,
            "base_value": deed.base_value,
            "created_at": deed.created_at,
        }
        for deed in deeds
    ]
