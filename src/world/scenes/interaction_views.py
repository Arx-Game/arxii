from __future__ import annotations

from datetime import timedelta
from http import HTTPMethod
from typing import Any

from django.db import transaction
from django.db.models import Prefetch, QuerySet
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.interaction_filters import (
    InteractionFavoriteFilter,
    InteractionFilter,
    InteractionReactionFilter,
)
from world.scenes.interaction_link_services import auto_link_pose_to_actions
from world.scenes.interaction_permissions import (
    CanViewInteraction,
    IsInteractionWriter,
    get_account_personas,
    get_account_roster_entries,
)
from world.scenes.interaction_serializers import (
    InteractionDetailSerializer,
    InteractionFavoriteSerializer,
    InteractionListSerializer,
    InteractionReactionSerializer,
    PoseSubmitSerializer,
)
from world.scenes.interaction_services import (
    create_interaction,
    delete_interaction,
    mark_very_private,
)
from world.scenes.models import (
    Interaction,
    InteractionAction,
    InteractionFavorite,
    InteractionReaction,
    Persona,
    Scene,
)
from world.scenes.place_models import InteractionReceiver


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

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        entries = get_account_roster_entries(self.request)
        context["roster_entry_ids"] = {e.pk for e in entries} if entries else set()
        return context

    def get_queryset(self) -> QuerySet[Interaction]:
        base_qs = Interaction.objects.select_related(
            "persona__character_sheet",
            "persona__character_sheet__roster_entry",
            "persona",
            "scene",
            "place",
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
                "receivers",
                queryset=InteractionReceiver.objects.select_related("persona"),
                to_attr="cached_receivers",
            ),
            Prefetch(
                "reactions",
                queryset=InteractionReaction.objects.all(),
                to_attr="cached_reactions",
            ),
            Prefetch(
                "action_links",
                queryset=InteractionAction.objects.select_related("action_interaction"),
                to_attr="cached_action_links",
            ),
        )

        persona_ids = get_account_personas(self.request)

        user = self.request.user
        if user.is_staff:
            # Staff sees everything EXCEPT very_private
            return base_qs.exclude(visibility=InteractionVisibility.VERY_PRIVATE)

        if not persona_ids:
            # No personas: show only public interactions (with time bound for pruning)
            default_since = timezone.now() - timedelta(days=90)
            since_filter = self.request.query_params.get("since")  # noqa: USE_FILTERSET
            time_bound = (
                {"timestamp__gte": since_filter}
                if since_filter
                else {"timestamp__gte": default_since}
            )
            public_ids = (
                Interaction.objects.filter(
                    scene__privacy_mode=ScenePrivacyMode.PUBLIC,
                    visibility=InteractionVisibility.DEFAULT,
                    **time_bound,
                )
                .values("pk")
                .union(
                    Interaction.objects.filter(
                        scene__isnull=True,
                        place__isnull=True,
                        visibility=InteractionVisibility.DEFAULT,
                        **time_bound,
                    )
                    .exclude(mode=InteractionMode.WHISPER)
                    .values("pk"),
                )
            )
            return base_qs.filter(pk__in=public_ids)

        # Default time bound for partition pruning. Without this, the UNION
        # subquery scans all monthly partitions. The 'since' filter param
        # overrides this when provided by the frontend.
        default_since = timezone.now() - timedelta(days=90)
        since_filter = self.request.query_params.get("since")  # noqa: USE_FILTERSET
        if since_filter:
            # Frontend provided an explicit time bound — use it for pruning
            time_bound = {"timestamp__gte": since_filter}
        else:
            time_bound = {"timestamp__gte": default_since}

        # UNION subquery for visibility filtering — each branch hits one index
        # and includes a timestamp bound for partition pruning. UNION
        # deduplicates, so no .distinct() needed.
        visible_ids = (
            Interaction.objects.filter(
                persona_id__in=persona_ids,
                **time_bound,
            )
            .values("pk")
            .union(
                Interaction.objects.filter(
                    receivers__persona_id__in=persona_ids,
                    **time_bound,
                ).values("pk"),
                Interaction.objects.filter(
                    scene__privacy_mode=ScenePrivacyMode.PUBLIC,
                    visibility=InteractionVisibility.DEFAULT,
                    **time_bound,
                ).values("pk"),
                Interaction.objects.filter(
                    scene__isnull=True,
                    place__isnull=True,
                    visibility=InteractionVisibility.DEFAULT,
                    **time_bound,
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
        persona_ids = get_account_personas(request)
        if not persona_ids or interaction.persona_id not in persona_ids:
            return Response(
                {"detail": "You are not the writer of this interaction."},
                status=status.HTTP_403_FORBIDDEN,
            )
        writer_persona = Persona.objects.get(pk=interaction.persona_id)
        deleted = delete_interaction(interaction, writer_persona)
        if not deleted:
            return Response(
                {"detail": "Cannot delete this interaction (too old or not yours)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="mark-private")
    def mark_private(self, request: Request, pk: int | None = None) -> Response:
        interaction = self.get_object()
        persona_ids = get_account_personas(request)
        if not persona_ids:
            return Response(
                {"detail": "No personas found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Try each persona -- mark_very_private checks receiver/writer internally
        personas = Persona.objects.filter(pk__in=persona_ids)
        for persona in personas:
            mark_very_private(interaction, persona)
        serializer = self.get_serializer(interaction)
        return Response(serializer.data)

    @action(detail=False, methods=[HTTPMethod.POST], url_path="submit-pose")
    def submit_pose(self, request: Request) -> Response:
        """Create a POSE Interaction and auto-link prior ACTION Interactions.

        Accepts ``action_link_ids`` for an explicit override:
        - Absent (key missing): auto-link is run.
        - Present as a list (even empty): exact links are created; auto-link skipped.
        """
        serializer = PoseSubmitSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        persona = Persona.objects.get(pk=data["persona_id"])
        scene: Scene | None = (
            Scene.objects.get(pk=data["scene_id"]) if data.get("scene_id") else None
        )

        with transaction.atomic():
            interaction = create_interaction(
                persona=persona,
                content=data["content"],
                mode=InteractionMode.POSE,
                scene=scene,
            )

            action_link_ids: list[int] | None = data.get("action_link_ids")
            if action_link_ids is not None:
                # Explicit override: create exactly the supplied links in order,
                # skipping auto-link entirely (empty list = caller opted out).
                InteractionAction.objects.bulk_create(
                    [
                        InteractionAction(
                            pose=interaction,
                            action_interaction_id=aid,
                            ordering=i,
                        )
                        for i, aid in enumerate(action_link_ids)
                    ]
                )
            else:
                auto_link_pose_to_actions(interaction)

        # The freshly-created interaction has not been through get_queryset()'s
        # Prefetch pipeline, so the cached_* to_attr attributes used by
        # InteractionListSerializer do not exist yet. Set them to empty lists
        # to avoid AttributeError on serialization; a new pose has no receivers,
        # target personas, favorites, or reactions.
        interaction.cached_receivers = []
        interaction.cached_target_personas = []
        interaction.cached_favorites = []
        interaction.cached_reactions = []
        interaction.cached_action_links = []
        out_serializer = InteractionListSerializer(
            interaction, context=self.get_serializer_context()
        )
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


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
        roster_entries = get_account_roster_entries(self.request)
        if not roster_entries:
            return InteractionFavorite.objects.none()
        return InteractionFavorite.objects.filter(roster_entry__in=roster_entries).order_by(
            "-timestamp"
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Toggle a favorite on or off for the authenticated user."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        interaction = serializer.validated_data["interaction"]
        roster_entries = get_account_roster_entries(request)
        if not roster_entries:
            return Response(
                {"detail": "No roster entries found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Use the first roster entry for favorites
        roster_entry = roster_entries[0]
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
            timestamp=interaction.timestamp,
            roster_entry=roster_entry,
        )
        return Response(
            InteractionFavoriteSerializer(favorite).data,
            status=status.HTTP_201_CREATED,
        )


class InteractionReactionViewSet(viewsets.ModelViewSet):
    """Toggle emoji reactions on interactions."""

    serializer_class = InteractionReactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = InteractionFavoritePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = InteractionReactionFilter
    http_method_names = ["post", "delete"]

    def get_queryset(self) -> QuerySet[InteractionReaction]:
        return InteractionReaction.objects.filter(account=self.request.user).order_by("-pk")

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Toggle: delete if exists, create if not."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        interaction = serializer.validated_data["interaction"]
        emoji = serializer.validated_data["emoji"]
        existing = InteractionReaction.objects.filter(
            interaction=interaction,
            account=request.user,
            emoji=emoji,
        ).first()
        if existing:
            existing.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        reaction = InteractionReaction.objects.create(
            interaction=interaction,
            timestamp=interaction.timestamp,
            account=request.user,
            emoji=emoji,
        )
        return Response(
            InteractionReactionSerializer(reaction).data,
            status=status.HTTP_201_CREATED,
        )
