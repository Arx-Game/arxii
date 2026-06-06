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
    FAME_TIER_ORDER,
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


def build_renown_payload(
    persona: Persona,
    *,
    viewer_society=None,
    deeds_limit: int = 20,
) -> dict:
    """Assemble the renown payload for ``persona``.

    When ``viewer_society`` is supplied, the fame block's
    ``tier`` / ``tier_label`` / ``tier_multiplier`` are computed using
    that society's ``fame_perception_offset`` (#738) — an insular
    society reads a Celebrity through their lens as merely Talked
    About, etc. When None, the raw tier is shown.
    """
    return {
        "persona_id": persona.pk,
        "persona_name": persona.name,
        "prestige": _build_prestige(persona),
        "fame": _build_fame(persona, viewer_society=viewer_society),
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


def _build_fame(persona: Persona, *, viewer_society=None) -> dict:
    tier = _apply_perception_offset(persona.fame_tier, viewer_society)
    next_tier_name, next_threshold = _next_tier_after(tier)
    return {
        "points": persona.fame_points,
        "tier": tier,
        "tier_label": FameTier(tier).label,
        "tier_multiplier": FAME_TIER_MULTIPLIERS[tier],
        "next_tier": next_tier_name,
        "next_tier_threshold": next_threshold,
    }


def _apply_perception_offset(tier: str, viewer_society) -> str:
    """#738 — Subtract viewer society's perception offset from displayed tier.

    Offset is ≤0 (insular societies hear less). Floors at NORMAL.
    Returns the raw tier when viewer_society is None or offset is 0.
    """
    if viewer_society is None:
        return tier
    offset = viewer_society.fame_perception_offset or 0
    if offset == 0:
        return tier
    tier_index = FAME_TIER_ORDER.index(tier)
    adjusted_index = max(0, tier_index + offset)
    return FAME_TIER_ORDER[adjusted_index]


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


# ---------------------------------------------------------------------------
# #744 — Renown card: the limited view a viewer sees on someone else's sheet.
#
# Per the spec:
# * Fame tier label only (no numeric points, no multiplier).
# * Deeds: visible iff ``deed.societies_aware`` intersects the viewer's
#   persona's society memberships.
# * Reputation: rows for societies the viewer is a member of (the viewer
#   knows what their own circles think; nothing else).
# * Perception offset applied via the viewer's first society (deterministic
#   default; per-society lensing is a future refinement).
# ---------------------------------------------------------------------------


class _RenownCardFameSerializer(serializers.Serializer):
    """Fame block on the card — tier label only.

    The full Renown tab exposes numeric fame_points + multiplier for
    the player's own personas; foreign personas show just the tier
    label (the spec is explicit about no numeric reveal).
    """

    tier = serializers.CharField()
    tier_label = serializers.CharField()


class RenownCardSerializer(serializers.Serializer):
    """Limited renown view of ``target_persona`` for a foreign viewer."""

    persona_id = serializers.IntegerField()
    persona_name = serializers.CharField()
    fame = _RenownCardFameSerializer()
    visible_deeds = _DeedSerializer(many=True)
    visible_reputation = _SocietyReputationSerializer(many=True)


def build_renown_card_payload(
    target_persona: Persona,
    *,
    viewer_persona: Persona | None,
    deeds_limit: int = 20,
) -> dict:
    """Assemble the filtered renown card payload for a foreign viewer.

    ``viewer_persona`` is the persona the viewer is presenting. When
    None, the card surfaces only the always-public bits: name + raw
    fame tier label (which is what a stranger would observe).
    """
    viewer_society_ids = _viewer_society_ids(viewer_persona)
    primary_viewer_society = _viewer_primary_society(viewer_persona)
    adjusted_tier = _apply_perception_offset(target_persona.fame_tier, primary_viewer_society)
    return {
        "persona_id": target_persona.pk,
        "persona_name": target_persona.name,
        "fame": {
            "tier": adjusted_tier,
            "tier_label": FameTier(adjusted_tier).label,
        },
        "visible_deeds": _build_card_visible_deeds(
            target_persona, viewer_society_ids, limit=deeds_limit
        ),
        "visible_reputation": _build_card_visible_reputation(target_persona, viewer_society_ids),
    }


def _viewer_society_ids(viewer_persona: Persona | None) -> set[int]:
    """Set of society IDs the viewer's persona holds memberships in."""
    if viewer_persona is None:
        return set()
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return set(
        OrganizationMembership.objects.filter(persona=viewer_persona)
        .exclude(organization__society__isnull=True)
        .values_list("organization__society_id", flat=True)
        .distinct()
    )


def _viewer_primary_society(viewer_persona: Persona | None):
    """Pick a single society to gate the perception-offset lookup through.

    With multiple memberships we'd want per-society lensing in principle,
    but the card surfaces one tier label. v1: alphabetically-first
    society (deterministic; switchable via explicit persona context in a
    future iteration).
    """
    if viewer_persona is None:
        return None
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    membership = (
        OrganizationMembership.objects.filter(persona=viewer_persona)
        .exclude(organization__society__isnull=True)
        .select_related("organization__society")
        .order_by("organization__society__name")
        .first()
    )
    return membership.organization.society if membership else None


def _build_card_visible_deeds(
    target_persona: Persona,
    viewer_society_ids: set[int],
    *,
    limit: int,
) -> list[dict]:
    """Deeds whose ``societies_aware`` intersects the viewer's societies."""
    if not viewer_society_ids:
        return []
    deeds = (
        LegendEntry.objects.filter(persona=target_persona, societies_aware__in=viewer_society_ids)
        .distinct()
        .order_by("-created_at")[:limit]
    )
    return [
        {
            "id": deed.pk,
            "title": deed.title,
            "base_value": deed.base_value,
            "created_at": deed.created_at,
        }
        for deed in deeds
    ]


def _build_card_visible_reputation(
    target_persona: Persona,
    viewer_society_ids: set[int],
) -> list[dict]:
    """Reputation rows for societies the viewer is a member of."""
    if not viewer_society_ids or not target_persona.is_established_or_primary:
        return []
    rows = (
        SocietyReputation.objects.filter(persona=target_persona, society_id__in=viewer_society_ids)
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
