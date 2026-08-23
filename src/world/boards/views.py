"""Read-only DRF views for the boards API (#3286).

Writes (post/edit/remove) go through action dispatch (ADR-0001) — no create/
update/destroy here. ORG board visibility is gated on active membership
(mirrors ``world.tasking.views.OrgTaskViewSet.get_queryset``); LOCATION
board reads are public by design (nothing private about a room's notice
board).
"""

from __future__ import annotations

from django.db.models import Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.boards.filters import BoardFilterSet, BoardPostFilterSet
from world.boards.models import Board, BoardPost
from world.boards.serializers import BoardPostSerializer, BoardSerializer
from world.boards.services import (
    exclude_blocked_and_muted_board_authors,
    visible_posts_for_board,
)
from world.tasking.permissions import active_persona_for_request


class BoardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


def _visible_board_ids(request: Request) -> QuerySet[int] | list[int]:
    """Board ids the requesting account may read: every LOCATION board, plus
    ORG boards for organizations the requester's active persona belongs to."""
    persona = active_persona_for_request(request)
    location_boards = Q(room_profile__isnull=False)
    if persona is None:
        return Board.objects.filter(location_boards).values_list("pk", flat=True)

    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    member_org_ids = OrganizationMembership.objects.filter(
        persona=persona,
        left_at__isnull=True,
        exiled_at__isnull=True,
    ).values_list("organization_id", flat=True)
    org_boards = Q(organization_id__in=member_org_ids)
    return Board.objects.filter(location_boards | org_boards).values_list("pk", flat=True)


class BoardViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only board metadata: list/retrieve.

    LOCATION boards are visible to everyone; ORG boards only to active members.
    """

    serializer_class = BoardSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = BoardFilterSet
    pagination_class = BoardPagination

    def get_queryset(self) -> QuerySet[Board]:
        return Board.objects.filter(pk__in=_visible_board_ids(self.request)).select_related(
            "room_profile", "organization"
        )


class BoardPostViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only board posts: list/retrieve. Writes dispatch through Actions."""

    serializer_class = BoardPostSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = BoardPostFilterSet
    pagination_class = BoardPagination

    def get_queryset(self) -> QuerySet[BoardPost]:
        return (
            BoardPost.objects.active()
            .filter(board_id__in=_visible_board_ids(self.request))
            .select_related("board", "author_persona")
            .order_by("-created_at")
        )

    def list(self, request: Request, *args, **kwargs) -> Response:
        """List posts, applying the per-board display cap when ``?board=`` is given.

        Without a ``board`` filter, falls back to the plain filtered queryset
        (cross-board browsing has no single cap to apply).
        """
        # Read the raw query param (not the FilterSet) because this deliberately
        # takes a DIFFERENT code path from the FilterSet-driven queryset below
        # (the per-board display cap, ``visible_posts_for_board``) rather than
        # filtering the same base queryset.
        board_id = request.query_params.get("board")  # noqa: USE_FILTERSET
        if board_id is not None:
            board = Board.objects.filter(pk=board_id, pk__in=_visible_board_ids(request)).first()
            # A non-visible (or nonexistent) board resolves to an empty queryset —
            # flows through the same pagination path as every other list, rather
            # than short-circuiting to a bare list that breaks the paginated
            # response shape callers expect.
            if board is not None:
                queryset = visible_posts_for_board(board)
            else:
                queryset = BoardPost.objects.none()
        else:
            queryset = self.filter_queryset(self.get_queryset())
        queryset = exclude_blocked_and_muted_board_authors(queryset, viewer_account=request.user)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return Response(self.get_serializer(queryset, many=True).data)
