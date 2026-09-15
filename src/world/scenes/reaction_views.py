"""REST surface for reaction windows (#904)."""

from __future__ import annotations

from http import HTTPMethod

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from web.api.pagination import DefaultPagination
from world.scenes.constants import ReactionWindowKind
from world.scenes.interaction_permissions import get_account_personas
from world.scenes.interaction_services import can_view_interaction
from world.scenes.models import Interaction, Persona, SceneParticipation
from world.scenes.reaction_models import ReactionWindow, WindowReaction
from world.scenes.reaction_services import (
    ReactionKindConfig,
    get_reaction_kind,
    react_to_interaction,
    react_to_window,
)
from world.scenes.services import active_persona_for_sheet


class WindowReactInputSerializer(serializers.Serializer):
    persona_id = serializers.IntegerField(
        help_text="PK of the Persona reacting (must belong to the requester)."
    )
    choice = serializers.CharField(
        max_length=64, help_text="Slug from the window's choices payload."
    )


class InteractionReactInputSerializer(WindowReactInputSerializer):
    interaction_id = serializers.IntegerField(help_text="PK of the Interaction to react to.")
    kind = serializers.ChoiceField(
        choices=ReactionWindowKind.choices,
        help_text="Window kind to open lazily (must be a lazy_open kind, e.g. kudos).",
    )


class PendingReactionWindowSerializer(serializers.Serializer):
    """One open, not-yet-reacted-to window for the caller's active persona (#2987).

    Deliberately thin: no reactor list, no counts. A hidden (``public=False``)
    kind like WITNESS must stay anonymous end to end, and even a public kind's
    pending entry has nothing to show yet since the viewer hasn't reacted.
    """

    id = serializers.IntegerField(source="pk")
    interaction_id = serializers.IntegerField()
    scene_id = serializers.IntegerField()
    kind = serializers.CharField()
    choices = serializers.SerializerMethodField()

    def get_choices(self, window: ReactionWindow) -> list[dict[str, str]]:
        config = self.context["kind_config"]
        return [{"slug": c.slug, "label": c.label} for c in config.choices_for(window)]


def _pending_paginated_response() -> serializers.Serializer:
    """Inline schema for ``pending``'s paginated list (mirrors the journal-list pattern)."""
    return inline_serializer(
        name="PaginatedPendingReactionWindowList",
        fields={
            "count": serializers.IntegerField(),
            "next": serializers.URLField(allow_null=True),
            "previous": serializers.URLField(allow_null=True),
            "results": PendingReactionWindowSerializer(many=True),
        },
    )


class ReactionWindowViewSet(viewsets.GenericViewSet):
    """POST /reaction-windows/{pk}/react/, plus GET /reaction-windows/pending/.

    Most reads ride the interaction feed (windows serialize inline on their
    event); all eligibility/validation for reacting lives in
    ``react_to_window``. ``react-to-interaction`` (#911) opens a lazy kind's
    window on first reaction: kudos-style kinds need no pre-existing window
    row. ``pending`` (#2987) is the one standalone read: the bystander-facing
    "what can I react to right now" list, needed because a WITNESS window
    (``public=False``) never surfaces in a feed a bystander wasn't scrolling;
    the reactor learns of it independently of any interaction they authored.
    """

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    queryset = ReactionWindow.objects.all()
    serializer_class = WindowReactInputSerializer
    permission_classes = [IsAuthenticated]

    def _owned_persona(self, request: Request, persona_id: int) -> Persona | None:
        if persona_id not in get_account_personas(request):
            return None
        return Persona.objects.get(pk=persona_id)

    @staticmethod
    def _reaction_response(reaction: WindowReaction, window_pk: int) -> Response:
        return Response(
            {
                "id": reaction.pk,
                "window": window_pk,
                "persona_id": reaction.reactor_persona_id,
                "choice": reaction.choice,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=[HTTPMethod.POST])
    def react(self, request: Request, pk: int | None = None) -> Response:
        window = self.get_object()
        serializer = WindowReactInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        persona = self._owned_persona(request, serializer.validated_data["persona_id"])
        if persona is None:
            return Response(
                {"detail": "You do not own this persona."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            reaction = react_to_window(
                window=window,
                reactor_persona=persona,
                choice=serializer.validated_data["choice"],
            )
        except DjangoValidationError as exc:
            messages = exc.messages if hasattr(exc, "messages") else ["Unable to react."]
            return Response({"detail": messages}, status=status.HTTP_400_BAD_REQUEST)

        return self._reaction_response(reaction, window.pk)

    @action(detail=False, methods=[HTTPMethod.POST], url_path="react-to-interaction")
    def react_to_interaction(self, request: Request) -> Response:
        serializer = InteractionReactInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        persona = self._owned_persona(request, data["persona_id"])
        if persona is None:
            return Response(
                {"detail": "You do not own this persona."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            interaction = Interaction.objects.get(pk=data["interaction_id"])
        except Interaction.DoesNotExist:
            return Response(
                {"detail": "No such interaction."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            reaction = react_to_interaction(
                interaction=interaction,
                kind=data["kind"],
                reactor_persona=persona,
                choice=data["choice"],
            )
        except DjangoValidationError as exc:
            messages = exc.messages if hasattr(exc, "messages") else ["Unable to react."]
            return Response({"detail": messages}, status=status.HTTP_400_BAD_REQUEST)

        return self._reaction_response(reaction, reaction.window_id)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="kind",
                type=str,
                required=False,
                description="ReactionWindowKind to list (defaults to witness).",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                required=False,
                description="Page number.",
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                required=False,
                description="Rows per page (default 50, max 200).",
            ),
        ],
        responses=_pending_paginated_response(),
    )
    @action(detail=False, methods=[HTTPMethod.GET])
    def pending(self, request: Request) -> Response:
        """Open windows of ``kind`` the caller's active persona can still react to.

        ``kind`` defaults to WITNESS (#2987's bystander-reaction menu); any
        registered ``ReactionWindowKind`` may be requested. Scoping mirrors
        ``react_to_window``'s eligibility (which additionally requires
        ``scene.is_active`` at reaction time): the account must be a
        scene participant (a public scene is otherwise visible to anyone,
        but that alone never made a non-participant a bystander) AND the
        persona must be able to see the witnessed interaction
        (``can_view_interaction``). Settled windows, the persona's own
        deeds, and windows already reacted to are excluded. Never exposes a
        reactor list; the response carries only the window's identity and
        its live choices.
        """
        # Custom-action param; FilterSets don't apply to detail=False actions.
        kind = request.query_params.get("kind", ReactionWindowKind.WITNESS)  # noqa: USE_FILTERSET
        valid_kinds = {value for value, _label in ReactionWindowKind.choices}
        if kind not in valid_kinds:
            return Response(
                {"detail": "Unknown reaction window kind."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from world.roster.services.selection import selected_character  # noqa: PLC0415

        character = selected_character(request.user)
        if character is None:
            return Response(
                {"detail": "Select a character to view pending reactions."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        persona = active_persona_for_sheet(character.sheet_data)

        try:
            config = get_reaction_kind(kind)
        except DjangoValidationError:
            # Valid enum value, but no consumer app registered it (e.g. not
            # installed) -- render an empty page rather than 500.
            return self._paginated_pending_response(
                ReactionWindow.objects.none(), request, config=None
            )

        participant_scene_ids = SceneParticipation.objects.filter(account=request.user).values_list(
            "scene_id", flat=True
        )
        candidates = (
            ReactionWindow.objects.filter(
                kind=kind,
                settled_at__isnull=True,
                scene_id__in=participant_scene_ids,
            )
            .exclude(interaction__persona_id=persona.pk)
            .exclude(reactions__reactor_persona_id=persona.pk)
            .select_related("interaction", "scene")
        )
        # Persona-level perception (can_view_interaction) is Python-side, so
        # narrow to visible pks and re-filter: pagination stays on a QuerySet.
        # can_view_interaction costs 1-2 queries per candidate window; bounded,
        # since candidates are only the unsettled windows of scenes the caller
        # participates in.
        visible_pks = [w.pk for w in candidates if can_view_interaction(w.interaction, persona)]
        visible = candidates.filter(pk__in=visible_pks)

        return self._paginated_pending_response(visible, request, config=config)

    @staticmethod
    def _paginated_pending_response(
        windows: QuerySet[ReactionWindow],
        request: Request,
        *,
        config: ReactionKindConfig | None,
    ) -> Response:
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(windows, request)
        serializer = PendingReactionWindowSerializer(
            page, many=True, context={"kind_config": config}
        )
        return paginator.get_paginated_response(serializer.data)
