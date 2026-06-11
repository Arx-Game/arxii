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


class _CategoryPolishSerializer(serializers.Serializer):
    """One polish category's value + derived tier label for a building."""

    category_id = serializers.IntegerField()
    category_name = serializers.CharField()
    value = serializers.IntegerField()
    tier_label = serializers.CharField(allow_null=True)


class _OwnedDwellingSerializer(serializers.Serializer):
    """One building the persona owns, with polish breakdown + upkeep state."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    polish_by_category = _CategoryPolishSerializer(many=True)
    upkeep_warning = serializers.BooleanField()
    decayed_features_count = serializers.IntegerField()
    dormant = serializers.BooleanField()
    dormant_since = serializers.DateTimeField(allow_null=True)


class _TenantedRoomSerializer(serializers.Serializer):
    """One room the persona tenants — polish breakdown only, no upkeep/dormancy.

    Upkeep + dormancy are building-level concepts; rooms don't carry
    them directly. The room's containing building's upkeep state shows
    up in ``owned_dwellings`` separately (when the persona owns it).
    """

    id = serializers.IntegerField()
    name = serializers.CharField()
    polish_by_category = _CategoryPolishSerializer(many=True)


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
    owned_dwellings = _OwnedDwellingSerializer(many=True)
    tenanted_rooms = _TenantedRoomSerializer(many=True)


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
    tier_resolver = _build_tier_label_resolver()
    return {
        "persona_id": persona.pk,
        "persona_name": persona.name,
        "prestige": _build_prestige(persona),
        "fame": _build_fame(persona, viewer_society=viewer_society),
        "reputation": _build_reputation(persona),
        "recent_deeds": _build_recent_deeds(persona, limit=deeds_limit),
        "owned_dwellings": _build_owned_dwellings(persona, tier_resolver),
        "tenanted_rooms": _build_tenanted_rooms(persona, tier_resolver),
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

    Anonymous-viewer fallback (no ``viewer_persona`` resolved) surfaces
    the lowest fame tier (NORMAL) — a viewer with no society context
    has no lens through which to recognise the subject's renown. Per
    spec: "essentially nothing visible until at least one deed becomes
    societies_aware for any society the viewer is in."
    """
    viewer_society_ids, primary_viewer_society = _viewer_societies(viewer_persona)
    if viewer_persona is None:
        adjusted_tier = FameTier.NORMAL.value
    else:
        adjusted_tier = _apply_perception_offset(target_persona.fame_tier, primary_viewer_society)
    return {
        "persona_id": target_persona.pk,
        "persona_name": target_persona.name,
        "fame": {
            "tier": adjusted_tier,
            "tier_label": FameTier(adjusted_tier).label,
        },
        "visible_deeds": _build_card_visible_deeds(
            target_persona,
            viewer_society_ids,
            limit=deeds_limit,
            viewer_persona=viewer_persona,
        ),
        "visible_reputation": _build_card_visible_reputation(target_persona, viewer_society_ids),
    }


def _viewer_societies(viewer_persona: Persona | None):
    """Return ``(set_of_society_ids, alphabetically_first_society)``.

    Single query: fetches every (society_id, society_name) pair for the
    viewer's memberships, picks the alphabetic minimum in Python for
    the perception-offset lookup. v1 doesn't expose per-society lensing
    so we don't need a queryset — a deterministic primary suffices.
    """
    if viewer_persona is None:
        return set(), None
    from world.societies.models import OrganizationMembership, Society  # noqa: PLC0415

    rows = list(
        OrganizationMembership.objects.filter(persona=viewer_persona)
        .exclude(organization__society__isnull=True)
        .values_list(
            "organization__society_id",
            "organization__society__name",
        )
        .distinct()
    )
    if not rows:
        return set(), None
    ids = {sid for sid, _ in rows}
    primary_sid = min(rows, key=lambda row: row[1])[0]
    primary_society = Society.objects.get(pk=primary_sid)
    return ids, primary_society


def _build_card_visible_deeds(
    target_persona: Persona,
    viewer_society_ids: set[int],  # noqa: ARG001 - kept for call-shape stability; union covers it
    *,
    limit: int,
    viewer_persona: Persona | None = None,
) -> list[dict]:
    """The target's deeds the VIEWER knows of (#902 union).

    Society awareness ∪ witnessed/heard-told knowledge ∪ common knowledge.
    Anonymous viewers (no persona) still see the target's common-knowledge
    deeds — a tale at 5× its base belongs to everyone.
    """
    from world.societies.knowledge_services import known_deed_ids  # noqa: PLC0415

    base = LegendEntry.objects.filter(persona=target_persona, is_active=True)
    if viewer_persona is None:
        from django.db.models import F, Sum  # noqa: PLC0415
        from django.db.models.functions import Coalesce  # noqa: PLC0415

        from world.societies.constants import COMMON_KNOWLEDGE_MULTIPLIER  # noqa: PLC0415

        deeds = (
            base.annotate(spread_total=Coalesce(Sum("spreads__value_added"), 0))
            .filter(
                base_value__gt=0,
                spread_total__gte=(COMMON_KNOWLEDGE_MULTIPLIER - 1) * F("base_value"),
            )
            .order_by("-created_at")[:limit]
        )
    else:
        deeds = base.filter(pk__in=known_deed_ids(viewer_persona)).order_by("-created_at")[:limit]
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


def _build_tier_label_resolver():
    """Return ``resolve(category_id, value) -> tier_name | None``.

    Bulk-fetches every ``TierThreshold`` row once + buckets by
    ``category_id`` so per-row label lookups are O(thresholds-per-cat)
    Python walks instead of one DB query each. With K dwellings × M
    categories per payload, this drops the threshold reads from K×M to
    exactly 1.
    """
    from world.buildings.models import TierThreshold  # noqa: PLC0415

    by_category: dict[int, list] = {}
    # Order descending so the first match in the walk is the highest tier
    # whose ``min_value`` ≤ the polish value.
    for threshold in TierThreshold.objects.order_by("category_id", "-min_value"):
        by_category.setdefault(threshold.category_id, []).append(threshold)

    def resolve(category_id: int, value: int) -> str | None:
        for threshold in by_category.get(category_id, []):
            if value >= threshold.min_value:
                return threshold.tier_name
        return None

    return resolve


def _build_owned_dwellings(persona: Persona, tier_resolver) -> list[dict]:
    """#742 — Per-owned-building polish breakdown + upkeep state.

    For each building this persona owns, surface the polish-by-category
    rows (with tier labels), an upkeep_warning flag (any instance with
    consecutive_missed_upkeep > 0), the decayed-features count, and the
    dormancy state. Empty list when the persona owns nothing.
    """
    from django.db.models import Prefetch  # noqa: PLC0415

    from world.buildings.models import (  # noqa: PLC0415
        Building,
        BuildingPolish,
        BuildingProjectInstance,
    )

    # ``to_attr`` is omitted intentionally — using it on a
    # SharedMemoryModel parent (Building) leaks the cached list across
    # requests via the identity map (see feedback_prefetch_to_attr_leaks).
    # Without ``to_attr`` the prefetch attaches to ``_prefetched_objects_cache``
    # which the standard manager reads through on each request.
    buildings = (
        Building.objects.filter(owner_persona=persona)
        .select_related("area")
        .prefetch_related(
            Prefetch(  # noqa: PREFETCH_STRING — see comment above re identity-map leak.
                "polish_by_category",
                queryset=BuildingPolish.objects.select_related("category"),
            ),
            Prefetch(  # noqa: PREFETCH_STRING — see comment above.
                "project_instances",
                queryset=BuildingProjectInstance.objects.only(
                    "pk", "building_id", "consecutive_missed_upkeep", "decayed_at"
                ),
            ),
        )
    )
    return [_serialize_owned_building(b, tier_resolver) for b in buildings]


def _serialize_owned_building(building, tier_resolver) -> dict:
    polish_rows = [
        {
            "category_id": row.category_id,
            "category_name": row.category.name,
            "value": row.value,
            "tier_label": tier_resolver(row.category_id, row.value),
        }
        for row in building.polish_by_category.all()
    ]
    instances = list(building.project_instances.all())
    upkeep_warning = any(inst.consecutive_missed_upkeep > 0 for inst in instances)
    decayed_count = sum(1 for inst in instances if inst.decayed_at is not None)
    return {
        "id": building.pk,
        "name": building.area.name,
        "polish_by_category": polish_rows,
        "upkeep_warning": upkeep_warning,
        "decayed_features_count": decayed_count,
        "dormant": not building.is_accessible,
        "dormant_since": building.dormant_since,
    }


def _build_tenanted_rooms(persona: Persona, tier_resolver) -> list[dict]:
    """#742 — Rooms the persona tenants, with polish breakdown.

    Spec symmetry with ``owned_dwellings``: a persona credited with
    ``prestige_from_dwellings`` via room tenancy needs the corresponding
    per-room visibility. Upkeep / dormancy live on the containing
    building, not the room, so this surface stays polish-only.

    Includes rooms that the persona tenants *in their own building* —
    those rooms double-count in ``prestige_from_dwellings`` (the spec's
    intentional owner-tenant double-count), and surfacing them here
    matches that mental model.
    """
    from django.db.models import Prefetch  # noqa: PLC0415

    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.buildings.models import RoomPolish  # noqa: PLC0415

    rooms = (
        RoomProfile.objects.filter(tenant_persona=persona)
        .select_related("objectdb")
        .prefetch_related(
            Prefetch(  # noqa: PREFETCH_STRING — see _build_owned_dwellings re identity-map.
                "polish_by_category",
                queryset=RoomPolish.objects.select_related("category"),
            ),
        )
    )
    return [_serialize_tenanted_room(room, tier_resolver) for room in rooms]


def _serialize_tenanted_room(room, tier_resolver) -> dict:
    polish_rows = [
        {
            "category_id": row.category_id,
            "category_name": row.category.name,
            "value": row.value,
            "tier_label": tier_resolver(row.category_id, row.value),
        }
        for row in room.polish_by_category.all()
    ]
    return {
        "id": room.pk,
        "name": room.objectdb.db_key,
        "polish_by_category": polish_rows,
    }
