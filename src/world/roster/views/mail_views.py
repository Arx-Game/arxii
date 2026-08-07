"""Views for player mail."""

from http import HTTPMethod
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
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
from world.scenes.block_services import blocked_player_ids_for
from world.scenes.mute_services import account_muted


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
        """Return mail for the authenticated player sorted by newest first.

        Blocked senders' mail is excluded entirely (#2996 Decision 2) — the write path that
        created it is untouched (the sender's own response is unaffected), suppression is
        query-time exclusion on the recipient's read. Muted senders' mail is NOT excluded here
        — it's auto-filed (read + archived) at create time instead (``perform_create``), so it
        stays visible, just already handled.
        """
        try:
            player_data = self.request.user.player_data
        except AttributeError:
            return PlayerMail.objects.none()
        qs = PlayerMail.objects.filter(recipient_tenure__player_data=player_data)
        blocked_ids = blocked_player_ids_for(player_data)
        if blocked_ids:
            qs = qs.exclude(sender_tenure__player_data_id__in=blocked_ids)
        return qs.select_related(
            "sender_tenure__player_data__account",
            "sender_tenure__roster_entry__character_sheet__character",
            "recipient_tenure__roster_entry__character_sheet__character",
        ).order_by("-sent_date")

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Validate sender tenure ownership before saving, then ping the recipient.

        The write always succeeds and returns normally regardless of block/mute (#2996
        Decision 2 — write-then-filter; skip-the-write would leak). A muted sender's mail is
        auto-filed on the recipient's side immediately after the row is created: stamped
        read + archived, the deliberate simplification documented in the spec (unmute can't
        later distinguish auto-filed from hand-archived).

        The auto-file mutation happens on the SAME row the sender's own create response
        serializes, so ``serializer.data`` is force-cached BEFORE that mutation — otherwise the
        sender's response would show the recipient's auto-filed state and leak the mute back to
        them (the exact byte-identity invariant #2996's write-then-filter contract requires).
        """
        sender_tenure = serializer.validated_data["sender_tenure"]
        if (
            not self.request.user.is_staff
            and sender_tenure.player_data != self.request.user.player_data
        ):
            msg = "Cannot send mail as this character."
            raise PermissionDenied(msg)
        mail = serializer.save()
        # Freeze the sender-facing representation before any post-save mutation below.
        _ = serializer.data
        sender_player = mail.sender_tenure.player_data if mail.sender_tenure_id else None
        recipient_player = mail.recipient_tenure.player_data
        if (
            sender_player is not None
            and recipient_player is not None
            and account_muted(viewer_player=recipient_player, target_player=sender_player)
        ):
            mail.read_date = timezone.now()
            mail.archived = True
            mail.save(update_fields=["read_date", "archived"])
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
