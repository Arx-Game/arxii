"""Read-only missives API (#3289): the acting character's letters, sent and received.

Writing, reading (marking read), accepting and refusing go through the registry actions
(``actions/definitions/missives.py``) over websocket dispatch; this API only lists. The
rows are ``services.visible_missives_for``: everything the character sent, and what it
received once arrived and not suppressed by a block.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import BooleanField, ExpressionWrapper, QuerySet, Value
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from world.messengers.display import display_map_for
from world.messengers.filters import VIEWER_SENT, MissiveFilterSet
from world.messengers.models import Missive, MissiveAttachment
from world.messengers.serializers import MissiveSerializer
from world.messengers.services import sent_by_q, unread_count_for, visible_missives_for

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

_ENTRY_ID = OpenApiParameter(
    "entry_id",
    int,
    required=False,
    description="The roster entry this tab acts as (#3479).",
)


class MissivePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


def _entry_id_param(request: Request) -> int | None:
    """The tab's ``entry_id`` query parameter (#3479), or None when absent.

    The identity parameter every per-tab read takes; not a filter, so it is read here
    rather than through the FilterSet (``world/worship/views.py``).
    """
    raw = request.query_params.get("entry_id")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"entry_id": "A valid integer is required."}) from exc


def _viewer_sheet(request: Request) -> CharacterSheet | None:
    """The sheet of the character this request acts as, or None when it plays nobody."""
    from world.roster.services.selection import character_for_request  # noqa: PLC0415

    character = character_for_request(request, entry_id=_entry_id_param(request))
    if character is None:
        return None
    try:
        return character.character_sheet
    except ObjectDoesNotExist:
        return None


def _attachments_by_missive(missives: Sequence[Missive]) -> dict[int, list[MissiveAttachment]]:
    """Every attachment on these missives in one query, grouped by missive pk.

    Loaded fresh per request instead of prefetched: a prefetch onto the identity-mapped
    missive rows would serve a stale list after an accept or refuse (ADR-0263).
    """
    grouped: dict[int, list[MissiveAttachment]] = defaultdict(list)
    attachments = (
        MissiveAttachment.objects.filter(missive_id__in=[missive.pk for missive in missives])
        .select_related("item__template")
        .order_by("pk")
    )
    for attachment in attachments:
        grouped[attachment.missive_id].append(attachment)
    return grouped


@extend_schema(parameters=[_ENTRY_ID])
class MissiveViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    """The acting character's missives, newest first.

    Filters: ``direction`` (``received`` | ``sent``) and ``unread`` (received and not yet
    read). A request that plays no character sees an empty list.
    """

    serializer_class = MissiveSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MissiveFilterSet
    pagination_class = MissivePagination

    def get_queryset(self) -> QuerySet[Missive]:
        # For the generic machinery (schema generation); list and retrieve resolve the
        # viewer once and call _missives_for themselves.
        return self._missives_for(_viewer_sheet(self.request))

    @staticmethod
    def _missives_for(sheet: CharacterSheet | None) -> QuerySet[Missive]:
        """What ``sheet`` may see, newest first; one arrival settle per call."""
        if sheet is None:
            return Missive.objects.none().annotate(**{VIEWER_SENT: Value(False)})
        return (
            visible_missives_for(sheet)
            .annotate(
                **{VIEWER_SENT: ExpressionWrapper(sent_by_q(sheet), output_field=BooleanField())}
            )
            .order_by("-sent_at", "-pk")
        )

    def _serialize(
        self, missives: Sequence[Missive], sheet: CharacterSheet | None, *, many: bool
    ) -> Any:
        context = self.get_serializer_context()
        context["viewer_sheet"] = sheet
        context["attachments_by_missive"] = _attachments_by_missive(missives)
        context["names"] = display_map_for(sheet, missives) if sheet is not None else {}
        instance = missives if many else missives[0]
        return MissiveSerializer(instance, many=many, context=context).data

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        sheet = _viewer_sheet(request)
        queryset = self.filter_queryset(self._missives_for(sheet))
        page = self.paginate_queryset(queryset)
        missives = list(page) if page is not None else list(queryset)
        data = self._serialize(missives, sheet, many=True)
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        sheet = _viewer_sheet(request)
        missive = get_object_or_404(self._missives_for(sheet), pk=kwargs["pk"])
        self.check_object_permissions(request, missive)
        return Response(self._serialize([missive], sheet, many=False))

    @extend_schema(
        responses=inline_serializer(
            name="MissiveUnreadCount", fields={"count": serializers.IntegerField()}
        )
    )
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request: Request) -> Response:
        """How many arrived missives to the acting character it has not read yet."""
        sheet = _viewer_sheet(request)
        count = unread_count_for(sheet) if sheet is not None else 0
        return Response({"count": count})
