"""
API views for progression endpoints.

Note: This module uses a custom APIView rather than ViewSet because it aggregates
data from multiple models (XP, Kudos, transactions) into a single dashboard response.
Converting to ViewSet pattern would require going through Account with complex
nested serializers, which would be more complex without clear benefit for this
read-only dashboard endpoint.
"""

from typing import cast

from evennia.accounts.models import AccountDB
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.progression.models import (
    ExperiencePointsData,
    KudosClaimCategory,
    KudosPointsData,
    KudosTransaction,
    XPTransaction,
)
from world.progression.serializers import AccountProgressionSerializer
from world.progression.services.kudos import InsufficientKudosError, claim_kudos_for_xp

# Default and maximum transaction limit for pagination
DEFAULT_TRANSACTION_LIMIT = 50
MAX_TRANSACTION_LIMIT = 200


def _build_progression_response(request: Request) -> Response:
    """Build the standard account progression response."""
    account = request.user

    try:
        limit = int(request.query_params.get("limit", DEFAULT_TRANSACTION_LIMIT))
        limit = max(1, min(limit, MAX_TRANSACTION_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_TRANSACTION_LIMIT

    try:
        offset = int(request.query_params.get("offset", 0))
        offset = max(0, offset)
    except (TypeError, ValueError):
        offset = 0

    xp_data = ExperiencePointsData.objects.filter(account=account).first()
    kudos_data = KudosPointsData.objects.filter(account=account).first()

    xp_transactions = (
        XPTransaction.objects.filter(account=account)
        .select_related("character")
        .order_by("-transaction_date")[offset : offset + limit]
    )

    kudos_transactions = (
        KudosTransaction.objects.filter(account=account)
        .select_related("source_category", "claim_category", "awarded_by")
        .order_by("-transaction_date")[offset : offset + limit]
    )

    claim_categories = KudosClaimCategory.objects.filter(is_active=True)

    data = {
        "xp": xp_data,
        "kudos": kudos_data,
        "xp_transactions": xp_transactions,
        "kudos_transactions": kudos_transactions,
        "claim_categories": claim_categories,
    }

    serializer = AccountProgressionSerializer(data)
    return Response(serializer.data)


class AccountProgressionView(APIView):
    """
    Get the current user's progression data (XP and Kudos).

    Returns XP balance, Kudos balance, recent transactions, and claim options.

    Query Parameters:
        limit (int): Maximum number of transactions to return per type.
                     Default: 50, Max: 200
        offset (int): Number of transactions to skip (for pagination).
                      Default: 0
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Return current user's XP and Kudos data (read-only)."""
        return _build_progression_response(request)


class ClaimKudosView(APIView):
    """
    Claim kudos and convert to XP.

    POST body: { "claim_category_id": int, "amount": int }
    Returns: Updated account progression data.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Claim kudos for XP conversion."""
        claim_category_id = request.data.get("claim_category_id")
        amount = request.data.get("amount")

        if claim_category_id is None or amount is None:
            return Response(
                {"detail": "claim_category_id and amount are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return Response(
                {"detail": "amount must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            claim_category = KudosClaimCategory.objects.get(
                id=claim_category_id,
                is_active=True,
            )
        except KudosClaimCategory.DoesNotExist:
            return Response(
                {"detail": "Invalid or inactive claim category."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            claim_kudos_for_xp(
                account=cast(AccountDB, request.user),
                amount=amount,
                claim_category=claim_category,
            )
        except InsufficientKudosError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return _build_progression_response(request)
