"""#930 prep — member-gated read API for an organization's books.

One composite payload per org: treasury, graft, income streams, debts,
obligations, recent contributions, and the recent ledger. The React
family-books / management screen reads this; nothing here mutates. Books
are visible to any active member of the org (rank-gating spend authority
is a separate, existing concern — ``spend_rank_max`` ships in the payload
so the UI can show who may spend).
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.currency.models import (
    ContributionRecord,
    CurrencyTransfer,
    DebtInstrument,
    OrgIncomeStream,
    OrgObligation,
)
from world.currency.services import get_or_create_economics, get_or_create_treasury

_MSG_NO_ORG = "No such organization."
_MSG_NOT_MEMBER = "You are not a member of that organization."
_RECENT_ROWS = 50


class IncomeStreamRowSerializer(serializers.Serializer):
    name = serializers.CharField()
    kind = serializers.CharField()
    gross_amount = serializers.IntegerField()
    active = serializers.BooleanField()


class DebtRowSerializer(serializers.Serializer):
    creditor = serializers.CharField()
    principal = serializers.IntegerField()
    arrears = serializers.IntegerField()
    interest_bps_monthly = serializers.IntegerField()
    diverting = serializers.BooleanField()
    in_default = serializers.BooleanField()


class ObligationRowSerializer(serializers.Serializer):
    name = serializers.CharField()
    to_organization = serializers.CharField()
    percent = serializers.IntegerField()
    active = serializers.BooleanField()


class ContributionRowSerializer(serializers.Serializer):
    persona_name = serializers.CharField()
    amount = serializers.IntegerField()
    reason = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class LedgerRowSerializer(serializers.Serializer):
    amount = serializers.IntegerField()
    reason = serializers.CharField()
    direction = serializers.CharField()  # "in" | "out"
    created_at = serializers.DateTimeField()


class OrgBooksSerializer(serializers.Serializer):
    """The whole books page in one read."""

    organization_id = serializers.IntegerField()
    organization_name = serializers.CharField()
    balance = serializers.IntegerField()
    spend_rank_max = serializers.IntegerField()
    graft_pct = serializers.IntegerField()
    income_streams = IncomeStreamRowSerializer(many=True)
    debts = DebtRowSerializer(many=True)
    obligations = ObligationRowSerializer(many=True)
    contributions = ContributionRowSerializer(many=True)
    ledger = LedgerRowSerializer(many=True)


class OrgBooksViewSet(viewsets.ViewSet):
    """Retrieve-only: GET /org-books/{org_id}/ — the member-visible books.

    No list endpoint: books are reached from an org you belong to, not
    browsed. Mirrors RankingDisplayViewSet's diegetic posture.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: OrgBooksSerializer,
            403: OpenApiResponse(description="Not a member of the organization."),
            404: OpenApiResponse(description="No such organization."),
        },
    )
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
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

        payload = _books_payload(organization)
        return Response(OrgBooksSerializer(payload).data)


def _viewer_persona(request: Request):
    """The viewer's presented persona (PRIMARY convention), or None."""
    from world.scenes.services import (  # noqa: PLC0415
        MissingPrimaryPersonaError,
        persona_for_character,
    )

    try:
        puppet = request.user.puppet
    except AttributeError:
        return None
    if puppet is None:
        return None
    try:
        return persona_for_character(puppet)
    except MissingPrimaryPersonaError:
        return None


def _books_payload(organization) -> dict:
    treasury = get_or_create_treasury(organization)
    economics = get_or_create_economics(organization)

    transfers_in = CurrencyTransfer.objects.filter(to_treasury=treasury)[:_RECENT_ROWS]
    transfers_out = CurrencyTransfer.objects.filter(from_treasury=treasury)[:_RECENT_ROWS]
    ledger = sorted(
        [
            *(
                {
                    "amount": t.amount,
                    "reason": t.reason,
                    "direction": "in",
                    "created_at": t.created_at,
                }
                for t in transfers_in
            ),
            *(
                {
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

    return {
        "organization_id": organization.pk,
        "organization_name": organization.name,
        "balance": treasury.balance,
        "spend_rank_max": treasury.spend_rank_max,
        "graft_pct": economics.graft_pct,
        "income_streams": [
            {"name": s.name, "kind": s.kind, "gross_amount": s.gross_amount, "active": s.active}
            for s in OrgIncomeStream.objects.filter(organization=organization)
        ],
        "debts": [
            {
                "creditor": d.creditor_organization.name,
                "principal": d.principal,
                "arrears": d.arrears,
                "interest_bps_monthly": d.interest_bps_monthly,
                "diverting": d.diverting,
                "in_default": d.in_default,
            }
            for d in DebtInstrument.objects.filter(
                debtor_organization=organization, active=True
            ).select_related("creditor_organization")
        ],
        "obligations": [
            {
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
