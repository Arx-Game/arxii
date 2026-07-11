"""Views for player mail."""

from http import HTTPMethod
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from world.roster.models import PlayerMail
from world.roster.serializers import PlayerMailSerializer, UnreadMailCountSerializer
from world.roster.services.mail_notifications import notify_mail_arrived


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
                "sender_tenure__roster_entry__character_sheet__character",
                "recipient_tenure__roster_entry__character_sheet__character",
            )
            .order_by("-sent_date")
        )

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Validate sender tenure ownership before saving, then ping the recipient."""
        sender_tenure = serializer.validated_data["sender_tenure"]
        if (
            not self.request.user.is_staff
            and sender_tenure.player_data != self.request.user.player_data
        ):
            msg = "Cannot send mail as this character."
            raise PermissionDenied(msg)
        mail = serializer.save()
        # Deferred via transaction.on_commit (the notify_battle_state_changed pattern,
        # battles/services.py) so the ping never fires on a row a concurrent reader can't
        # yet see -- fires correctly under autocommit even though this view has no
        # explicit atomic block.
        recipient_tenure = mail.recipient_tenure
        transaction.on_commit(lambda: notify_mail_arrived(recipient_tenure, mail))

    @extend_schema(request=None, responses=PlayerMailSerializer, tags=["roster"])
    @action(detail=True, methods=[HTTPMethod.POST], url_path="mark-read")
    def mark_read(self, request: Request, pk: int | None = None) -> Response:
        """Mark this mail as read (idempotent). Recipient-only via the scoped queryset."""
        mail = self.get_object()
        mail.mark_read()
        serializer = self.get_serializer(mail)
        return Response(serializer.data)

    @extend_schema(responses=UnreadMailCountSerializer, tags=["roster"])
    @action(detail=False, methods=[HTTPMethod.GET], url_path="unread-count")
    def unread_count(self, request: Request) -> Response:
        """Count of unread, unarchived mail across the requester's tenures."""
        count = self.get_queryset().filter(read_date__isnull=True, archived=False).count()
        serializer = UnreadMailCountSerializer({"count": count})
        return Response(serializer.data)
