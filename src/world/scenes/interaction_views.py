from __future__ import annotations

from http import HTTPMethod
from typing import Any

from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.interaction_filters import InteractionFavoriteFilter, InteractionFilter
from world.scenes.interaction_permissions import CanViewInteraction, IsInteractionWriter
from world.scenes.interaction_serializers import (
    InteractionDetailSerializer,
    InteractionFavoriteSerializer,
    InteractionListSerializer,
)
from world.scenes.interaction_services import delete_interaction, mark_very_private
from world.scenes.interaction_utils import get_roster_entry_from_request
from world.scenes.models import (
    Interaction,
    InteractionAudience,
    InteractionFavorite,
    Persona,
)


class InteractionCursorPagination(CursorPagination):
    page_size = 50
    ordering = "-timestamp"
    cursor_query_param = "cursor"
    cursor_query_description = "The pagination cursor value."


class InteractionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for browsing interactions with destroy and mark_private actions."""

    filter_backends = [DjangoFilterBackend]
    filterset_class = InteractionFilter
    pagination_class = InteractionCursorPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Interaction]:
        base_qs = Interaction.objects.select_related(
            "character",
            "persona",
            "location",
            "scene",
            "roster_entry",
        ).prefetch_related(
            Prefetch(
                "target_personas",
                queryset=Persona.objects.all(),
                to_attr="cached_target_personas",
            ),
            Prefetch(
                "favorites",
                queryset=InteractionFavorite.objects.all(),
                to_attr="cached_favorites",
            ),
            Prefetch(
                "audience",
                queryset=InteractionAudience.objects.select_related("persona"),
                to_attr="cached_audience",
            ),
        )

        roster_entry = get_roster_entry_from_request(self.request)
        if roster_entry is None:
            return base_qs.none()

        user = self.request.user
        if user.is_staff:
            # Staff sees everything EXCEPT very_private
            return base_qs.exclude(visibility=InteractionVisibility.VERY_PRIVATE)

        # UNION subquery for visibility filtering — each branch hits one index
        # instead of a 4-way BitmapOr. UNION deduplicates, so no .distinct() needed.
        visible_ids = (
            Interaction.objects.filter(roster_entry=roster_entry)
            .values("pk")
            .union(
                Interaction.objects.filter(
                    audience__roster_entry=roster_entry,
                ).values("pk"),
                Interaction.objects.filter(
                    scene__privacy_mode=ScenePrivacyMode.PUBLIC,
                    visibility=InteractionVisibility.DEFAULT,
                ).values("pk"),
                Interaction.objects.filter(
                    scene__isnull=True,
                    visibility=InteractionVisibility.DEFAULT,
                )
                .exclude(mode=InteractionMode.WHISPER)
                .values("pk"),
            )
        )
        return base_qs.filter(pk__in=visible_ids)

    def get_serializer_class(
        self,
    ) -> type[BaseSerializer[Interaction]]:
        if self.action == "retrieve":
            return InteractionDetailSerializer
        return InteractionListSerializer

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "destroy":
            return [IsAuthenticated(), IsInteractionWriter()]
        if self.action == "retrieve":
            return [IsAuthenticated(), CanViewInteraction()]
        return [permission() for permission in self.permission_classes]

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        interaction = self.get_object()
        roster_entry = get_roster_entry_from_request(request)
        if roster_entry is None:
            return Response(
                {"detail": "No active character found."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted = delete_interaction(interaction, roster_entry)
        if not deleted:
            return Response(
                {"detail": "Cannot delete this interaction (too old or not yours)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="mark-private")
    def mark_private(self, request: Request, pk: int | None = None) -> Response:
        interaction = self.get_object()
        roster_entry = get_roster_entry_from_request(request)
        if roster_entry is None:
            return Response(
                {"detail": "No active character found."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        mark_very_private(interaction, roster_entry)
        serializer = self.get_serializer(interaction)
        return Response(serializer.data)


class InteractionFavoritePagination(PageNumberPagination):
    page_size = 50


class InteractionFavoriteViewSet(viewsets.ModelViewSet):
    """ViewSet for toggling interaction favorites."""

    serializer_class = InteractionFavoriteSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = InteractionFavoritePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = InteractionFavoriteFilter
    http_method_names = ["post", "delete", "get"]

    def get_queryset(self) -> QuerySet[InteractionFavorite]:
        roster_entry = get_roster_entry_from_request(self.request)
        if roster_entry is None:
            return InteractionFavorite.objects.none()
        return InteractionFavorite.objects.filter(roster_entry=roster_entry)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Toggle a favorite on or off for the authenticated user."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        interaction = serializer.validated_data["interaction"]
        roster_entry = get_roster_entry_from_request(request)
        if roster_entry is None:
            return Response(
                {"detail": "No active character found."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted, _ = InteractionFavorite.objects.filter(
            interaction=interaction,
            roster_entry=roster_entry,
        ).delete()
        if deleted:
            return Response(
                {"detail": "Favorite removed."},
                status=status.HTTP_200_OK,
            )
        favorite = InteractionFavorite.objects.create(
            interaction=interaction,
            roster_entry=roster_entry,
        )
        return Response(
            InteractionFavoriteSerializer(favorite).data,
            status=status.HTTP_201_CREATED,
        )
