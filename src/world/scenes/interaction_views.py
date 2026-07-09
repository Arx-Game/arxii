from __future__ import annotations

from http import HTTPMethod
from typing import Any

from django.db import transaction
from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from world.magic.models import CharacterResonance, PoseEndorsement, SceneEntryEndorsement
from world.scenes.block_services import hidden_persona_ids_for_viewer
from world.scenes.constants import (
    InteractionMode,
    PersonaType,
    PoseKind,
    ReactionWindowKind,
)
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
    ReactionEmojiSerializer,
)
from world.scenes.interaction_services import (
    create_interaction,
    delete_interaction,
    mark_very_private,
    push_interaction,
)
from world.scenes.models import (
    Interaction,
    InteractionAction,
    InteractionFavorite,
    InteractionReaction,
    Persona,
    ReactionEmoji,
    Scene,
)
from world.scenes.place_models import InteractionReceiver
from world.scenes.reaction_models import ReactionWindow, WindowReaction
from world.scenes.reaction_services import open_reaction_window
from world.scenes.reaction_toggle_services import (
    toggle_interaction_favorite,
    toggle_interaction_reaction,
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

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        entries = get_account_roster_entries(self.request)
        context["roster_entry_ids"] = {e.pk for e in entries} if entries else set()
        # The viewer's own character sheets — who their PersonaDiscovery rows belong to,
        # for per-viewer persona-name resolution (#1109).
        context["viewer_sheet_ids"] = {e.character_sheet_id for e in entries} if entries else set()
        # #1279 — staff are universal discoverers: they see real identities behind masks
        # everywhere, not just in the report detail serializer.
        context["is_staff"] = self.request.user.is_staff
        # Per-viewer my_reaction on reaction windows (#904) — context, never
        # Prefetch(to_attr) on the shared instances.
        context["persona_ids"] = set(get_account_personas(self.request))
        # Viewer's character sheet PKs — used for my_pose_endorsement and
        # entry_endorsed_by_me (#1138).
        context["character_sheet_ids"] = (
            {e.character_sheet_id for e in entries} if entries else set()
        )
        # Scene-entry endorsements indexed by endorsee_sheet_id — loaded once
        # per list request, keyed by the scene query param (#1138).
        scene_id = self.request.query_params.get("scene")  # noqa: USE_FILTERSET
        entry_map: dict[int, list] = {}
        if scene_id:
            rows = (
                SceneEntryEndorsement.objects.filter(scene_id=scene_id)
                .select_related("endorser_sheet", "resonance")
                .prefetch_related(
                    Prefetch(
                        "endorser_sheet__personas",
                        queryset=Persona.objects.filter(persona_type=PersonaType.PRIMARY),
                        to_attr="cached_primary_persona",
                    )
                )
            )
            for r in rows:
                entry_map.setdefault(r.endorsee_sheet_id, []).append(r)
        context["scene_entry_endorsements"] = entry_map
        return context

    def get_queryset(self) -> QuerySet[Interaction]:
        # Deferred: world.combat imports world.scenes at module scope elsewhere;
        # importing CombatRoundAction lazily keeps this view free of an import cycle.
        from world.combat.models import CombatRoundAction  # noqa: PLC0415
        from world.magic.models.dramatic_moment import DramaticMomentTag  # noqa: PLC0415

        base_qs = Interaction.objects.select_related(
            "persona__character_sheet",
            "persona__character_sheet__roster_entry",
            "persona__character_sheet__gender",  # #1109: apparent gender for anonymous sdesc
            "persona",
            "scene",
            "place",
        ).prefetch_related(
            Prefetch(
                "persona__character_sheet__resonances",
                queryset=CharacterResonance.objects.select_related("resonance"),
                to_attr="cached_resonances",
            ),
            Prefetch(
                "endorsements",
                queryset=PoseEndorsement.objects.select_related(
                    "endorser_sheet", "resonance"
                ).prefetch_related(
                    Prefetch(
                        "endorser_sheet__personas",
                        queryset=Persona.objects.filter(persona_type=PersonaType.PRIMARY),
                        to_attr="cached_primary_persona",
                    )
                ),
                to_attr="cached_endorsements",
            ),
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
            # has_critical_effect (#996): attach each linked ACTION's
            # CombatRoundAction(s) + focused opponent to the action_interaction
            # instances as `cached_round_actions`. A separate top-level path
            # prefetch (not nested inside the to_attr queryset above, where a
            # two-hop prefetch through the select_related forward FK fails to
            # attach). SharedMemoryModel shares instances by pk, so this lands on
            # the very same action_interaction objects cached_action_links exposes.
            Prefetch(
                "action_links__action_interaction__combat_round_actions",
                queryset=CombatRoundAction.objects.select_related("focused_opponent_target"),
                to_attr="cached_round_actions",
            ),
            Prefetch(
                "reaction_windows",
                queryset=ReactionWindow.objects.prefetch_related(
                    Prefetch(
                        "reactions",
                        queryset=WindowReaction.objects.select_related("reactor_persona"),
                        to_attr="cached_reaction_rows",
                    )
                ),
                to_attr="cached_reaction_windows",
            ),
            Prefetch(
                "dramatic_moment_tags",
                queryset=DramaticMomentTag.objects.select_related("moment_type"),
                to_attr="cached_dramatic_moment_tags",
            ),
        )

        # Read-visibility lives on the Interaction queryset so the scene highlight reel
        # (#1241) shares the exact same gate — no parallel privacy implementation.
        user = self.request.user
        persona_ids = get_account_personas(self.request) if user.is_authenticated else []
        since = self.request.query_params.get("since")  # noqa: USE_FILTERSET
        qs = base_qs.visible_to(user, persona_ids=persona_ids, since=since)
        # #1278 — hide personas the viewer can't see (Block, enforced, staff bypass).
        # Muted personas (#2087) are NOT excluded here — their interactions stay in the
        # feed with content blanked by the serializer ("actions still show without text").
        exclude_persona_ids: set[int] = set()
        if not user.is_staff:
            exclude_persona_ids = hidden_persona_ids_for_viewer(viewer_account=user)
        if exclude_persona_ids:
            qs = qs.exclude(persona_id__in=exclude_persona_ids)
        return qs

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

        pose_kind = data.get("pose_kind", PoseKind.STANDARD)
        with transaction.atomic():
            interaction = create_interaction(
                persona=persona,
                content=data["content"],
                mode=InteractionMode.POSE,
                scene=scene,
                pose_kind=pose_kind,
            )
            if pose_kind == PoseKind.ENTRY and scene is not None:
                # #904 — an entrance is a reactable moment; the window stays
                # open (and reactable) until the scene closes.
                open_reaction_window(interaction=interaction, kind=ReactionWindowKind.ENTRANCE)

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

        # Broadcast after commit so clients that refetch on receipt see committed state.
        # A fresh REST pose has no receiver/target rows; passing empty lists here
        # explicitly skips push_interaction's fallback DB queries (per its docstring).
        push_interaction(
            interaction,
            receiver_persona_ids=[],
            target_persona_ids=[],
            receiver_characters=[],
        )

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
        interaction.cached_dramatic_moment_tags = []
        interaction.cached_endorsements = []
        # ENTRY poses opened a window above; let the serializer query it (no
        # cached attr) so the fresh response includes the reactable strip.
        interaction.cached_reaction_windows = None
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
        created, favorite = toggle_interaction_favorite(
            interaction=interaction,
            roster_entry=roster_entry,
        )
        if not created:
            return Response(
                {"detail": "Favorite removed."},
                status=status.HTTP_200_OK,
            )
        return Response(
            InteractionFavoriteSerializer(favorite).data,
            status=status.HTTP_201_CREATED,
        )


class InteractionReactionViewSet(viewsets.ModelViewSet):
    """Toggle emoji reactions on interactions.

    A cataloged emoji with nonzero valence additionally fires an ambient
    relationship bump at the pose's author (#1699). The chip toggle is the
    primary behavior — a failed/deduped bump never blocks the reaction, and
    un-reacting never reverts a bump (the per-interaction unique constraint
    prevents re-farming).
    """

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
        created, reaction = toggle_interaction_reaction(
            interaction=interaction,
            account=request.user,  # type: ignore[invalid-argument-type]
            emoji=emoji,
        )
        if not created:
            return Response(status=status.HTTP_204_NO_CONTENT)
        bump_applied = self._maybe_apply_bump(request, interaction, emoji)
        return Response(
            {**InteractionReactionSerializer(reaction).data, "bump_applied": bump_applied},
            status=status.HTTP_201_CREATED,
        )

    def _maybe_apply_bump(self, request: Request, interaction: Any, emoji: str) -> bool:
        """Fire the relationship bump for a valenced catalog emoji; never raise."""
        from actions.definitions.relationships import RelationshipBumpAction  # noqa: PLC0415

        catalog_entry = ReactionEmoji.objects.filter(emoji=emoji, is_active=True).first()
        if catalog_entry is None or catalog_entry.valence == 0:
            return False
        actor = getattr(request.user, "puppet", None)  # noqa: GETATTR_LITERAL
        if actor is None:
            return False
        author_persona = interaction.persona
        if author_persona is None or author_persona.character_sheet is None:
            return False
        result = RelationshipBumpAction().run(
            actor=actor,
            target_sheet=author_persona.character_sheet,
            valence=catalog_entry.valence,
            interaction=interaction,
            source_emoji=catalog_entry,
        )
        return result.success


class ReactionEmojiViewSet(viewsets.ReadOnlyModelViewSet):
    """The active reaction-emoji catalog the scene footer renders (#1699)."""

    serializer_class = ReactionEmojiSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = InteractionFavoritePagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["valence"]
    http_method_names = ["get"]

    def get_queryset(self) -> QuerySet[ReactionEmoji]:
        return ReactionEmoji.objects.filter(is_active=True)
