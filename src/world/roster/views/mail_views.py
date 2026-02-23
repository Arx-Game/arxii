"""Views for player mail."""

from typing import Any

from django.db.models import QuerySet
from rest_framework import mixins, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.serializers import BaseSerializer

from world.roster.models import PlayerMail
from world.roster.serializers import PlayerMailSerializer


class PlayerMailPagination(PageNumberPagination):
    """Pagination for player mail."""

    page_size = 20


class PlayerMailViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """List and send player mail."""

    serializer_class = PlayerMailSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PlayerMailPagination

    def get_queryset(self) -> QuerySet[PlayerMail]:
        """Return mail for the authenticated player sorted by newest first."""
        try:
            player_data = self.request.user.player_data
        except AttributeError:
            return PlayerMail.objects.none()
        return (
            PlayerMail.objects.filter(recipient_tenure__player_data=player_data)
            .select_related(
                "sender_tenure__player_data__account",
                "sender_tenure__roster_entry__character",
                "recipient_tenure__roster_entry__character",
            )
            .order_by("-sent_date")
        )

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Validate sender tenure ownership before saving."""
        sender_tenure = serializer.validated_data["sender_tenure"]
        if (
            not self.request.user.is_staff
            and sender_tenure.player_data != self.request.user.player_data
        ):
            msg = "Cannot send mail as this character."
            raise PermissionDenied(msg)
        serializer.save()
