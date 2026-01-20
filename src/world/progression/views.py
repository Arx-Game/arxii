"""
API views for progression endpoints.

Note: This module uses a custom APIView rather than ViewSet because it aggregates
data from multiple models (XP, Kudos, transactions) into a single dashboard response.
Converting to ViewSet pattern would require going through Account with complex
nested serializers, which would be more complex without clear benefit for this
read-only dashboard endpoint.
"""

from rest_framework.permissions import IsAuthenticated
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

# Default and maximum transaction limit for pagination
DEFAULT_TRANSACTION_LIMIT = 50
MAX_TRANSACTION_LIMIT = 200


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

    def get(self, request):
        """Return current user's XP and Kudos data (read-only)."""
        account = request.user

        # Parse optional limit parameter
        try:
            limit = int(request.query_params.get("limit", DEFAULT_TRANSACTION_LIMIT))
            limit = max(1, min(limit, MAX_TRANSACTION_LIMIT))
        except (TypeError, ValueError):
            limit = DEFAULT_TRANSACTION_LIMIT

        # Parse optional offset parameter
        try:
            offset = int(request.query_params.get("offset", 0))
            offset = max(0, offset)
        except (TypeError, ValueError):
            offset = 0

        # Get existing data (read-only, no creation)
        # Records are created when XP/Kudos is first awarded via service layer
        xp_data = ExperiencePointsData.objects.filter(account=account).first()
        kudos_data = KudosPointsData.objects.filter(account=account).first()

        # Get transactions with configurable limit and offset
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

        # Get active claim categories
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
