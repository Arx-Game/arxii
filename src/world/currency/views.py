"""#930 prep — member-gated read API for an organization's books.

One composite payload per org: treasury, graft, income streams, debts,
obligations, recent contributions, and the recent ledger. The React
family-books / management screen reads this; nothing here mutates. Books
are visible to any active member of the org (rank-gating spend authority
is a separate, existing concern — ``spend_rank_max`` ships in the payload
so the UI can show who may spend).
"""

from __future__ import annotations

import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.character_sheets.models import CharacterSheet
from world.currency.models import (
    ContributionRecord,
    CurrencyTransfer,
    DebtInstrument,
    OrgIncomeStream,
    OrgObligation,
)
from world.currency.serializers import CharacterPurseSerializer
from world.currency.services import (
    get_or_create_economics,
    get_or_create_purse,
    get_or_create_treasury,
)
from world.roster.models import RosterEntry

logger = logging.getLogger(__name__)

_MSG_NO_ORG = "No such organization."
_MSG_NOT_MEMBER = "You are not a member of that organization."
_RECENT_ROWS = 50


class IncomeStreamRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    kind = serializers.CharField()
    gross_amount = serializers.IntegerField()
    uncollected_pool = serializers.IntegerField()
    active = serializers.BooleanField()


class DebtRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    creditor = serializers.CharField()
    summon_role_id = serializers.IntegerField(allow_null=True)
    principal = serializers.IntegerField()
    arrears = serializers.IntegerField()
    interest_bps_monthly = serializers.IntegerField()
    diverting = serializers.BooleanField()
    in_default = serializers.BooleanField()


class ObligationRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    to_organization = serializers.CharField()
    percent = serializers.IntegerField()
    active = serializers.BooleanField()


class ContributionRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    persona_name = serializers.CharField()
    amount = serializers.IntegerField()
    reason = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class LedgerRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    amount = serializers.IntegerField()
    reason = serializers.CharField()
    direction = serializers.CharField()  # "in" | "out"
    created_at = serializers.DateTimeField()


class MyBooksRowSerializer(serializers.Serializer):
    """One organization whose books the viewer may open."""

    organization_id = serializers.IntegerField()
    organization_name = serializers.CharField()
    rank = serializers.IntegerField()
    rank_title = serializers.CharField()


class OrgBooksSerializer(serializers.Serializer):
    """The whole books page in one read."""

    organization_id = serializers.IntegerField()
    organization_name = serializers.CharField()
    balance = serializers.IntegerField()
    spend_rank_max = serializers.IntegerField()
    graft_pct = serializers.IntegerField()
    steward_role_id = serializers.IntegerField(allow_null=True)
    uncollected_total = serializers.IntegerField()
    income_streams = IncomeStreamRowSerializer(many=True)
    debts = DebtRowSerializer(many=True)
    obligations = ObligationRowSerializer(many=True)
    contributions = ContributionRowSerializer(many=True)
    ledger = LedgerRowSerializer(many=True)


class OrgBooksViewSet(viewsets.ViewSet):
    """GET /org-books/{org_id}/ — the member-visible books.

    The list endpoint is the viewer's own shelf — only orgs the presented
    persona belongs to, never a browse of all orgs (the diegetic posture
    mirrors RankingDisplayViewSet).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: MyBooksRowSerializer(many=True)})
    def list(self, request: Request) -> Response:
        persona = _viewer_persona(request)
        if persona is None:
            return Response([])
        memberships = persona.organization_memberships.select_related(
            "organization", "organization__org_type", "rank"
        ).order_by("rank__tier", "organization__name")
        rows = [
            {
                "organization_id": m.organization.pk,
                "organization_name": m.organization.name,
                "rank": m.rank.tier,
                "rank_title": m.organization.get_rank_title(m.rank.tier),
            }
            for m in memberships
        ]
        return Response(MyBooksRowSerializer(rows, many=True).data)

    @extend_schema(
        responses={
            200: OrgBooksSerializer,
            403: OpenApiResponse(description="Not a member of the organization."),
            404: OpenApiResponse(description="No such organization."),
        },
    )
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        organization = _require_member_org(request, pk)
        payload = _books_payload(organization)
        return Response(OrgBooksSerializer(payload).data)


def _require_member_org(request: Request, pk: str | None):
    """The organization at ``pk``, or raise — gated to the viewer's membership."""
    from world.societies.models import Organization, OrganizationMembership  # noqa: PLC0415

    organization = Organization.objects.filter(pk=pk).first()
    if organization is None:
        raise NotFound(_MSG_NO_ORG)
    persona = _viewer_persona(request)
    is_member = (
        persona is not None
        and OrganizationMembership.objects.filter(
            persona=persona, organization=organization
        ).exists()
    )
    if not is_member:
        raise PermissionDenied(_MSG_NOT_MEMBER)
    return organization


def _viewer_persona(request: Request):
    """The viewer's ACTIVE persona (the face they're on), or None (#981).

    Gates books on whichever persona the player's character is currently
    presenting as — PRIMARY, an ESTABLISHED alt, or a TEMPORARY mask — so an
    ESTABLISHED persona's org books are reachable while that face is worn, and a
    player's *other* faces never leak. Fail-closed: no puppet / no sheet / a
    broken PRIMARY invariant all return None and the viewset denies.
    """
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        puppet = request.user.puppet
    except AttributeError:
        return None
    if puppet is None:
        return None
    sheet = puppet.character_sheet
    if sheet is None:
        return None
    try:
        return active_persona_for_sheet(sheet)
    except Exception:
        logger.exception("Persona resolution failed for sheet %s; denying", sheet.pk)
        return None


def _summon_roles_by_org(org_ids: list[int]) -> dict[int, int]:
    """org id -> an enabled NPCRole affiliated with it (the summonable face, #930).

    Lazy view-layer lookup: currency stays model-independent of npc_services;
    the books simply annotate which representative a line item can summon.
    """
    from world.npc_services.models import NPCRole  # noqa: PLC0415

    roles = (
        NPCRole.objects.filter(faction_affiliation_id__in=org_ids, is_active=True)
        .order_by("pk")
        .values_list("faction_affiliation_id", "pk")
    )
    by_org: dict[int, int] = {}
    for org_id, role_id in roles:
        by_org.setdefault(org_id, role_id)
    return by_org


def _books_payload(organization) -> dict:
    treasury = get_or_create_treasury(organization)
    economics = get_or_create_economics(organization)

    transfers_in = CurrencyTransfer.objects.filter(to_treasury=treasury)[:_RECENT_ROWS]
    transfers_out = CurrencyTransfer.objects.filter(from_treasury=treasury)[:_RECENT_ROWS]
    ledger = sorted(
        [
            *(
                {
                    "id": t.pk,
                    "amount": t.amount,
                    "reason": t.reason,
                    "direction": "in",
                    "created_at": t.created_at,
                }
                for t in transfers_in
            ),
            *(
                {
                    "id": t.pk,
                    "amount": t.amount,
                    "reason": t.reason,
                    "direction": "out",
                    "created_at": t.created_at,
                }
                for t in transfers_out
            ),
        ],
        key=lambda row: row["created_at"],
        reverse=True,
    )[:_RECENT_ROWS]

    debts = list(
        DebtInstrument.objects.filter(debtor_organization=organization, active=True).select_related(
            "creditor_organization"
        )
    )
    summon_roles = _summon_roles_by_org(
        [organization.pk, *(d.creditor_organization_id for d in debts)]
    )

    streams = list(OrgIncomeStream.objects.filter(organization=organization))
    return {
        "organization_id": organization.pk,
        "organization_name": organization.name,
        "balance": treasury.balance,
        "spend_rank_max": treasury.spend_rank_max,
        "graft_pct": economics.graft_pct,
        "steward_role_id": summon_roles.get(organization.pk),
        # #930 — what a collection dispatch would set out with, org-wide.
        "uncollected_total": sum(s.uncollected_pool for s in streams if s.active),
        "income_streams": [
            {
                "id": s.pk,
                "name": s.name,
                "kind": s.kind,
                "gross_amount": s.gross_amount,
                "uncollected_pool": s.uncollected_pool,
                "active": s.active,
            }
            for s in streams
        ],
        "debts": [
            {
                "id": d.pk,
                "creditor": d.creditor_organization.name,
                "summon_role_id": summon_roles.get(d.creditor_organization_id),
                "principal": d.principal,
                "arrears": d.arrears,
                "interest_bps_monthly": d.interest_bps_monthly,
                "diverting": d.diverting,
                "in_default": d.in_default,
            }
            for d in debts
        ],
        "obligations": [
            {
                "id": o.pk,
                "name": o.name,
                "to_organization": o.to_organization.name,
                "percent": o.percent,
                "active": o.active,
            }
            for o in OrgObligation.objects.filter(from_organization=organization).select_related(
                "to_organization"
            )
        ],
        "contributions": [
            {
                "id": c.pk,
                "persona_name": c.persona.name,
                "amount": c.amount,
                "reason": c.reason,
                "created_at": c.created_at,
            }
            for c in ContributionRecord.objects.filter(organization=organization).select_related(
                "persona"
            )[:_RECENT_ROWS]
        ],
        "ledger": ledger,
    }


class CharacterPurseView(APIView):
    """Read-only personal purse for the status surfaces (#1446).

    Visibility: staff, or an account with an active tenure on the character.
    Everyone else receives 404 (the vitals-view rule). Purse rows lazy-create
    at zero so a coinless character still reads cleanly.
    """

    permission_classes = [IsAuthenticated]

    def _can_view(self, request: Request, character_id: int) -> bool:
        if request.user.is_staff:
            return True
        return (
            RosterEntry.objects.for_account(request.user)
            .filter(character_sheet_id=character_id)
            .exists()
        )

    @extend_schema(responses=CharacterPurseSerializer)
    def get(self, request: Request, character_id: int) -> Response:
        if not self._can_view(request, character_id):
            raise NotFound
        try:
            sheet = CharacterSheet.objects.get(pk=character_id)
        except CharacterSheet.DoesNotExist:
            raise NotFound from None
        purse = get_or_create_purse(sheet)
        return Response(CharacterPurseSerializer(purse).data)
