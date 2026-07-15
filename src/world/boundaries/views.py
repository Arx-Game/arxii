"""ViewSets for the boundaries API (#1771 task 6, privacy-critical).

``PlayerBoundary``/``TreasuredSubject`` CRUD is owner-scoped self-authoring:
``get_queryset`` excludes every other player's rows, so a non-owner request
never reaches a hard-line row or a ``detail`` field belonging to someone
else — it 404s, same as ``world.consent``'s tenure-scoped viewsets.

The scene "lines & veils" aggregate is the one read surface that spans
multiple players' rows, and it is deliberately built from the ANONYMIZED
``world.boundaries.services.scene_lines_and_veils`` value object rather than
the raw models — see that service's docstring for the hard-line exclusion
guarantee.

Sign-off grant/withdraw and the GM stake-availability read operate on
stories-owned models (``Beat``, ``TreasuredSignoff``) and call
``world.stories.services.boundaries`` functions. Mounting them here would
make this app import ``world.stories`` (forbidden — ADR-0010 FK direction
specific->general; ``stories`` depends on ``boundaries``, never the
reverse). They live in ``world.stories.views``/``world.stories.serializers``
instead, mirroring the same dependency-direction call Task 5 made for the
``stake_availability``/``grant_treasured_signoff``/``withdraw_treasured_signoff``
service functions themselves (see ``world/stories/services/boundaries.py``).
"""

from __future__ import annotations

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.boundaries.models import ContentTheme, PlayerBoundary, TreasuredSubject
from world.boundaries.permissions import IsOwnPlayerData
from world.boundaries.serializers import (
    ContentThemeSerializer,
    PlayerBoundarySerializer,
    SceneLinesAndVeilsSerializer,
    TreasuredSubjectSerializer,
)
from world.boundaries.services import scene_lines_and_veils
from world.roster.models import RosterTenure
from world.scenes.models import Scene


class BoundariesPagination(PageNumberPagination):
    """Standard pagination for boundaries endpoints."""

    page_size = 50


class ContentThemeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for the staff-authored content theme catalog.

    Every authenticated player reads the same shared catalog to pick hard
    lines / tag advisories from — only staff configure it (via admin).
    """

    queryset = ContentTheme.objects.all()
    serializer_class = ContentThemeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["key", "is_active"]
    pagination_class = BoundariesPagination


class PlayerBoundaryViewSet(viewsets.ModelViewSet):
    """ViewSet for a player's own content boundaries (hard lines + advisories).

    Self-authoring only: ``get_queryset`` scopes to the requesting player's
    own rows, so another player's hard-line ``detail`` (or any row at all)
    is structurally unreachable through this endpoint — 404, not a filtered
    field.
    """

    serializer_class = PlayerBoundarySerializer
    permission_classes = [IsOwnPlayerData]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["kind", "theme"]
    pagination_class = BoundariesPagination

    def get_queryset(self) -> QuerySet[PlayerBoundary]:
        """Scope queryset to the requesting player's own boundaries."""
        try:
            return PlayerBoundary.objects.filter(
                owner=self.request.user.player_data,
            ).order_by("id")
        except AttributeError:
            return PlayerBoundary.objects.none()

    def perform_create(self, serializer: PlayerBoundarySerializer) -> None:
        """Force ``owner`` to the requesting player — never client-supplied."""
        if not hasattr(self.request.user, "player_data"):
            raise serializers.ValidationError(
                {"detail": "You must have player data to author a boundary."}
            )
        serializer.save(owner=self.request.user.player_data)


class TreasuredSubjectViewSet(viewsets.ModelViewSet):
    """ViewSet for a player's own treasured subjects (per-tenure attachments).

    Self-authoring only: ``get_queryset`` scopes to tenures owned by the
    requesting player.
    """

    serializer_class = TreasuredSubjectSerializer
    permission_classes = [IsOwnPlayerData]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["owner", "subject_kind"]
    pagination_class = BoundariesPagination

    def get_queryset(self) -> QuerySet[TreasuredSubject]:
        """Scope queryset to treasured subjects owned by the requesting player's tenures."""
        try:
            return TreasuredSubject.objects.filter(
                owner__player_data=self.request.user.player_data,
            ).order_by("id")
        except AttributeError:
            return TreasuredSubject.objects.none()


class SceneLinesAndVeilsView(APIView):
    """GET /api/boundaries/scenes/{scene_id}/lines-and-veils/?tenure={id}

    Read-only scene aggregate (#1771): the anonymized union of the scene's
    participants' shared ADVISORY boundaries + shared treasured subjects,
    filtered to what ``tenure`` (the requester's own tenure, validated
    below) is allowed to see. Hard lines are structurally excluded by the
    service layer, never by a filter here.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, scene_id: int) -> Response:
        scene = get_object_or_404(Scene, pk=scene_id)

        tenure_id = request.query_params.get("tenure")  # noqa: USE_FILTERSET — single-object APIView
        if not tenure_id:
            raise serializers.ValidationError({"tenure": "tenure query param is required."})

        player_data = request.user.player_data
        try:
            viewer_tenure = RosterTenure.objects.get(pk=tenure_id, player_data=player_data)
        except (RosterTenure.DoesNotExist, ValueError):
            raise NotFound from None

        result = scene_lines_and_veils(scene, viewer_tenure)
        return Response(SceneLinesAndVeilsSerializer(result).data)
