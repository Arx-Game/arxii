"""
API views for progression endpoints.
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


class AccountProgressionView(APIView):
    """
    Get the current user's progression data (XP and Kudos).

    Returns XP balance, Kudos balance, recent transactions, and claim options.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return current user's XP and Kudos data."""
        account = request.user

        # Get or create XP data
        xp_data, _ = ExperiencePointsData.objects.get_or_create(account=account)

        # Get or create Kudos data
        kudos_data, _ = KudosPointsData.objects.get_or_create(account=account)

        # Get recent transactions (last 50)
        xp_transactions = (
            XPTransaction.objects.filter(account=account)
            .select_related("character")
            .order_by("-transaction_date")[:50]
        )

        kudos_transactions = (
            KudosTransaction.objects.filter(account=account)
            .select_related("source_category", "claim_category", "awarded_by")
            .order_by("-transaction_date")[:50]
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
