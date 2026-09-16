"""The Deity Editor's API (#3780): staff only.

``/api/worship/admin/beings/`` lists, reads, creates and updates beings through
``editor_services.save_being``; ``options`` feeds every picker; the dashboard
actions aggregate what the other pantheon issues built.
"""

from __future__ import annotations

from typing import Any

from django.db.models import OuterRef, QuerySet, Subquery
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.clues.models import Clue
from world.codex.models import CodexEntry, OrganizationCodexGrant
from world.magic.models import Facet, Resonance
from world.societies.models import Organization
from world.stories.pagination import StandardResultsSetPagination
from world.tarot.models import TarotCard
from world.worship.constants import ConsecrationScope
from world.worship.editor_services import save_being
from world.worship.exceptions import EditorError
from world.worship.filters import StaffBeingFilterSet
from world.worship.models import (
    BeingNickname,
    ConsecrationTier,
    DevotionStanding,
    Prayer,
    Relic,
    ShrineDetails,
    TempleDedication,
    Vision,
    WorshipGrant,
    WorshippedBeing,
    WorshipRitePerformance,
    WorshipTradition,
)
from world.worship.staff_serializers import (
    CodexRowSerializer,
    EditorOptionsSerializer,
    OverviewSerializer,
    RelicRowSerializer,
    SiteRowSerializer,
    StaffBeingListSerializer,
    StaffBeingPageSerializer,
    StaffPrayerSerializer,
    StaffVisionSerializer,
    WorshipTabSerializer,
)

RECENT_ACTIVITY_ROWS = 12
TAB_ROWS = 50
PREREQUISITE_DEPTH = 6


def _save_or_400(page, *, being: WorshippedBeing | None = None) -> WorshippedBeing:
    try:
        return save_being(page, being=being)
    except EditorError as exc:
        raise ValidationError({"name": exc.user_message}) from exc


def _refs(rows) -> list[dict[str, Any]]:
    return [{"id": row.pk, "name": row.name} for row in rows]


class StaffBeingViewSet(viewsets.ModelViewSet):
    """Beings as the Deity Editor sees them. Sorted by pool, the way the list shows them."""

    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = StaffBeingFilterSet
    search_fields = ["name", "nicknames__name"]
    # No PATCH: the page is the truth, and a partial write would silently empty the
    # lists it omits. A partial request gets a real 405, not a 200 that lost data.
    http_method_names = ["get", "post", "put", "head", "options"]

    def get_queryset(self) -> QuerySet[WorshippedBeing]:
        # The tile's nickname comes as an annotation, not a prefetch: a to_attr
        # on an identity-mapped row would outlive the request.
        first_nickname = BeingNickname.objects.filter(being=OuterRef("pk")).order_by("pk")
        # The Obscure organization comes the same way, so a 100-tile list costs no
        # per-row grant query (the tier itself reads off the joined codex entry).
        obscure_org = OrganizationCodexGrant.objects.filter(entry=OuterRef("codex_entry")).order_by(
            "pk"
        )
        return (
            WorshippedBeing.objects.select_related("tradition", "codex_entry")
            .annotate(
                first_nickname=Subquery(first_nickname.values("name")[:1]),
                obscure_organization_name=Subquery(obscure_org.values("organization__name")[:1]),
            )
            .order_by("-resonance_pool", "name")
            .distinct()
        )

    def get_serializer_class(self):
        if self.action == "list":
            return StaffBeingListSerializer
        return StaffBeingPageSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = StaffBeingPageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        being = _save_or_400(serializer.to_page())
        return Response(StaffBeingPageSerializer(being).data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        being = self.get_object()
        serializer = StaffBeingPageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        being = _save_or_400(serializer.to_page(), being=being)
        return Response(StaffBeingPageSerializer(being).data)

    @action(detail=False, methods=["get"])
    def options(self, request: Request) -> Response:
        data = {
            "traditions": _refs(WorshipTradition.objects.order_by("name")),
            "resonances": _refs(Resonance.objects.order_by("name")),
            "facets": _refs(Facet.objects.order_by("name")),
            "tarot_cards": _refs(TarotCard.objects.order_by("name")),
            "organizations": _refs(Organization.objects.order_by("name")),
            "beings": _refs(WorshippedBeing.objects.order_by("name")),
        }
        return Response(EditorOptionsSerializer(data).data)

    @action(detail=True, methods=["get"])
    def overview(self, request: Request, pk: str | None = None) -> Response:
        being = self.get_object()
        top = (
            DevotionStanding.objects.filter(being=being)
            .select_related("character_sheet__character")
            .order_by("-favor")
            .first()
        )
        sites = (
            ShrineDetails.objects.filter(
                being=being, feature_instance__dissolved_at__isnull=True
            ).count()
            + TempleDedication.objects.filter(being=being, dissolved_at__isnull=True).count()
        )
        data = {
            "resonance_pool": being.resonance_pool,
            "lifetime_worship": being.lifetime_worship,
            "most_devoted_name": top.character_sheet.character.key if top else None,
            "most_devoted_favor": top.favor if top else None,
            "site_count": sites,
            "recent_activity": _recent_activity(being),
        }
        return Response(OverviewSerializer(data).data)

    @action(detail=True, methods=["get"])
    def worship(self, request: Request, pk: str | None = None) -> Response:
        being = self.get_object()
        return Response(WorshipTabSerializer(_worship_tab(being)).data)

    @action(detail=True, methods=["get"])
    def sites(self, request: Request, pk: str | None = None) -> Response:
        being = self.get_object()
        return Response(SiteRowSerializer(_site_rows(being), many=True).data)

    @action(detail=True, methods=["get"])
    def prayers(self, request: Request, pk: str | None = None) -> Response:
        being = self.get_object()
        rows = Prayer.objects.filter(being=being).select_related(
            "character_sheet__character", "room_profile__objectdb"
        )
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(StaffPrayerSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def visions(self, request: Request, pk: str | None = None) -> Response:
        being = self.get_object()
        rows = Vision.objects.filter(being=being).select_related("recipient__character", "sent_by")
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(StaffVisionSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def relics(self, request: Request, pk: str | None = None) -> Response:
        being = self.get_object()
        rows = Relic.objects.filter(being=being).select_related("item_instance__template")
        return Response(RelicRowSerializer(rows, many=True).data)

    @action(detail=True, methods=["get"])
    def codex(self, request: Request, pk: str | None = None) -> Response:
        being = self.get_object()
        return Response(CodexRowSerializer(_codex_rows(being), many=True).data)


def _recent_activity(being: WorshippedBeing) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(
        {
            "when": grant.created_at,
            "text": f"{_sheet_name(grant.granted_by)}: {grant.reason or 'worship'}",
            "note": f"+{grant.amount} pool",
        }
        for grant in WorshipGrant.objects.filter(being=being)
        .select_related("granted_by__character")
        .order_by("-created_at")[:RECENT_ACTIVITY_ROWS]
    )
    rows.extend(
        {
            "when": performance.performed_at,
            "text": (
                f"{_sheet_name(performance.character_sheet)} performed {performance.rite.name}"
            ),
            "note": f"favor +{performance.favor_granted}",
        }
        for performance in WorshipRitePerformance.objects.filter(rite__being=being)
        .select_related("character_sheet__character", "rite")
        .order_by("-performed_at")[:RECENT_ACTIVITY_ROWS]
    )
    rows.extend(
        {
            "when": prayer.prayed_at,
            "text": f"{_sheet_name(prayer.character_sheet)} prayed",
            "note": _prayer_note(prayer),
        }
        for prayer in Prayer.objects.filter(being=being)
        .select_related("character_sheet__character")
        .order_by("-prayed_at")[:RECENT_ACTIVITY_ROWS]
    )
    rows.extend(
        {
            "when": vision.sent_at,
            "text": f"A vision reached {_sheet_name(vision.recipient)}",
            "note": f"-{vision.resonance_spent} pool",
        }
        for vision in Vision.objects.filter(being=being)
        .select_related("recipient__character")
        .order_by("-sent_at")[:RECENT_ACTIVITY_ROWS]
    )
    rows.sort(key=lambda row: row["when"], reverse=True)
    return rows[:RECENT_ACTIVITY_ROWS]


def _sheet_name(sheet) -> str:
    return sheet.character.key if sheet is not None else "Someone"


def _prayer_note(prayer: Prayer) -> str:
    if prayer.intervention_id is not None:
        return "answered by a miracle"
    if prayer.dire_straits:
        return f"dire straits ({prayer.get_dire_straits_display().lower()})"
    if prayer.devotion_granted:
        return "act of devotion"
    return "plain prayer"


def _worship_tab(being: WorshippedBeing) -> dict[str, Any]:
    from world.ceremonies.models import CeremonyOffering  # noqa: PLC0415

    contributors = [
        {
            "character_name": grant.granted_by.character.key if grant.granted_by_id else "",
            "amount": grant.amount,
            "reason": grant.reason,
            "when": grant.created_at,
        }
        for grant in WorshipGrant.objects.filter(being=being)
        .select_related("granted_by__character")
        .order_by("-created_at")[:TAB_ROWS]
    ]
    offerings = [
        {
            "item_name": offering.item_name,
            "offered_by": offering.offered_by.name if offering.offered_by_id else "",
            "item_value": offering.item_value,
            "amount": offering.worship_grant.amount if offering.worship_grant_id else None,
            "ceremony_id": offering.ceremony_id,
            "when": offering.worship_grant.created_at if offering.worship_grant_id else None,
        }
        for offering in CeremonyOffering.objects.filter(ceremony__being=being)
        .select_related("offered_by", "worship_grant")
        .order_by("-pk")[:TAB_ROWS]
    ]
    most_devoted = [
        {
            "rank": index + 1,
            "character_name": standing.character_sheet.character.key,
            "favor": standing.favor,
            "lifetime_favor": standing.lifetime_favor,
            "valence": standing.valence,
        }
        for index, standing in enumerate(
            DevotionStanding.objects.filter(being=being)
            .select_related("character_sheet__character")
            .order_by("-favor")[:TAB_ROWS]
        )
    ]
    return {"contributors": contributors, "offerings": offerings, "most_devoted": most_devoted}


def _tier_for(scope: str, points: int) -> ConsecrationTier | None:
    return (
        ConsecrationTier.objects.filter(scope=scope, min_points__lte=points)
        .order_by("-min_points")
        .first()
    )


def _site_rows(being: WorshippedBeing) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for temple in (
        TempleDedication.objects.filter(being=being, dissolved_at__isnull=True)
        .select_related("building__area", "founder_character_sheet__character")
        .order_by("-consecration_points")
    ):
        tier = _tier_for(ConsecrationScope.TEMPLE, temple.consecration_points)
        rows.append(
            {
                "kind": "temple",
                "name": str(temple.building),
                "place": temple.building.area.name if temple.building.area_id else "",
                "consecration_points": temple.consecration_points,
                "tier_name": tier.name if tier else "",
                "bonus_percent": tier.bonus_percent if tier else 0,
                "founder_name": temple.founder_character_sheet.character.key
                if temple.founder_character_sheet_id
                else None,
            }
        )
    for shrine in (
        ShrineDetails.objects.filter(being=being, feature_instance__dissolved_at__isnull=True)
        .select_related(
            "feature_instance__room_profile__objectdb",
            "feature_instance__room_profile__area",
            "founder_character_sheet__character",
        )
        .order_by("-consecration_points")
    ):
        tier = _tier_for(ConsecrationScope.SHRINE, shrine.consecration_points)
        profile = shrine.feature_instance.room_profile
        rows.append(
            {
                "kind": "shrine",
                "name": profile.objectdb.key,
                "place": profile.area.name if profile.area_id else "",
                "consecration_points": shrine.consecration_points,
                "tier_name": tier.name if tier else "",
                "bonus_percent": tier.bonus_percent if tier else 0,
                "founder_name": shrine.founder_character_sheet.character.key
                if shrine.founder_character_sheet_id
                else None,
            }
        )
    return rows


def _codex_rows(being: WorshippedBeing) -> list[dict[str, Any]]:
    """The being's page, the entries it requires (chained), and the entries its
    visions' clues open: what a maintainer needs to see content-completeness."""
    relations = _page_and_prerequisites(being)
    for vision in Vision.objects.filter(being=being, clue__isnull=False).select_related(
        "clue__target_codex_entry"
    ):
        entry = vision.clue.target_codex_entry
        if entry is not None and entry.pk not in relations:
            relations[entry.pk] = (entry, f"opened by a vision's clue ({vision.clue.slug})")
    if not relations:
        return []
    entry_ids = list(relations)
    org_names: dict[int, list[str]] = {}
    for grant in OrganizationCodexGrant.objects.filter(entry_id__in=entry_ids).select_related(
        "organization"
    ):
        org_names.setdefault(grant.entry_id, []).append(grant.organization.name)
    clue_slugs: dict[int, list[str]] = {}
    for clue in Clue.objects.filter(target_codex_entry_id__in=entry_ids):
        clue_slugs.setdefault(clue.target_codex_entry_id, []).append(clue.slug)
    return [
        {
            "id": entry.pk,
            "name": entry.name,
            "is_public": entry.is_public,
            "relation": relation,
            "organizations": org_names.get(entry.pk, []),
            "clues": clue_slugs.get(entry.pk, []),
        }
        for entry, relation in relations.values()
    ]


def _page_and_prerequisites(being: WorshippedBeing) -> dict[int, tuple[CodexEntry, str]]:
    """The being's page and the prerequisite chain below it, bounded in depth."""
    relations: dict[int, tuple[CodexEntry, str]] = {}
    if being.codex_entry is None:
        return relations
    relations[being.codex_entry.pk] = (being.codex_entry, "the being's page")
    frontier = [being.codex_entry]
    for _ in range(PREREQUISITE_DEPTH):
        if not frontier:
            break
        next_frontier = []
        for entry in frontier:
            for prerequisite in entry.prerequisites.all():
                if prerequisite.pk not in relations:
                    relations[prerequisite.pk] = (prerequisite, f"required by {entry.name}")
                    next_frontier.append(prerequisite)
        frontier = next_frontier
    return relations
