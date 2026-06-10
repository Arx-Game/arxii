"""REST surface for reaction windows (#904)."""

from __future__ import annotations

from http import HTTPMethod

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.scenes.interaction_permissions import get_account_personas
from world.scenes.models import Persona
from world.scenes.reaction_models import ReactionWindow
from world.scenes.reaction_services import react_to_window


class WindowReactInputSerializer(serializers.Serializer):
    persona_id = serializers.IntegerField(
        help_text="PK of the Persona reacting (must belong to the requester)."
    )
    choice = serializers.CharField(
        max_length=64, help_text="Slug from the window's choices payload."
    )


class ReactionWindowViewSet(viewsets.GenericViewSet):
    """Action-only viewset: POST /reaction-windows/{pk}/react/.

    Reads ride the interaction feed (windows serialize inline on their
    event); all eligibility/validation lives in ``react_to_window``.
    """

    queryset = ReactionWindow.objects.all()
    serializer_class = WindowReactInputSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=[HTTPMethod.POST])
    def react(self, request: Request, pk: int | None = None) -> Response:
        window = self.get_object()
        serializer = WindowReactInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        persona_id = serializer.validated_data["persona_id"]
        if persona_id not in get_account_personas(request):
            return Response(
                {"detail": "You do not own this persona."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        persona = Persona.objects.get(pk=persona_id)

        try:
            reaction = react_to_window(
                window=window,
                reactor_persona=persona,
                choice=serializer.validated_data["choice"],
            )
        except DjangoValidationError as exc:
            messages = exc.messages if hasattr(exc, "messages") else ["Unable to react."]
            return Response({"detail": messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "id": reaction.pk,
                "window": window.pk,
                "persona_id": reaction.reactor_persona_id,
                "choice": reaction.choice,
            },
            status=status.HTTP_201_CREATED,
        )
