"""REST surface for reaction windows (#904)."""

from __future__ import annotations

from http import HTTPMethod

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.scenes.constants import ReactionWindowKind
from world.scenes.interaction_permissions import get_account_personas
from world.scenes.models import Interaction, Persona
from world.scenes.reaction_models import ReactionWindow, WindowReaction
from world.scenes.reaction_services import react_to_interaction, react_to_window


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


class ReactionWindowViewSet(viewsets.GenericViewSet):
    """Action-only viewset: POST /reaction-windows/{pk}/react/.

    Reads ride the interaction feed (windows serialize inline on their
    event); all eligibility/validation lives in ``react_to_window``.
    ``react-to-interaction`` (#911) opens a lazy kind's window on first
    reaction — kudos-style kinds need no pre-existing window row.
    """

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
