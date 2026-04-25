from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from world.narrative.filters import NarrativeMessageDeliveryFilter
from world.narrative.models import NarrativeMessageDelivery
from world.narrative.permissions import IsDeliveryRecipientOrStaff
from world.narrative.serializers import NarrativeMessageDeliverySerializer
from world.stories.pagination import StandardResultsSetPagination

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


class MyNarrativeMessagesView(ListAPIView):
    """List narrative message deliveries for the requesting account's character(s)."""

    serializer_class = NarrativeMessageDeliverySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = NarrativeMessageDeliveryFilter

    def get_queryset(self) -> "QuerySet[NarrativeMessageDelivery]":
        user = self.request.user
        return (
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet__character__db_account=user,
            )
            .select_related(
                "message",
                "message__related_story",
                "recipient_character_sheet__character",
            )
            .order_by("-message__sent_at")
        )


class MarkNarrativeMessageAcknowledgedView(APIView):
    """POST endpoint that marks a delivery acknowledged (idempotent)."""

    permission_classes = [IsAuthenticated, IsDeliveryRecipientOrStaff]

    def post(self, request: "Request", pk: int, *args: Any, **kwargs: Any) -> Response:
        delivery = get_object_or_404(NarrativeMessageDelivery, pk=pk)
        self.check_object_permissions(request, delivery)
        if delivery.acknowledged_at is None:
            delivery.acknowledged_at = timezone.now()
            delivery.save(update_fields=["acknowledged_at"])
        serializer = NarrativeMessageDeliverySerializer(delivery)
        return Response(serializer.data, status=status.HTTP_200_OK)
