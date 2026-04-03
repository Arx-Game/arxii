"""ViewSets for scene action requests."""

from __future__ import annotations

from http import HTTPMethod
from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.scenes.action_constants import ActionRequestStatus, DifficultyChoice
from world.scenes.action_filters import SceneActionRequestFilter
from world.scenes.action_models import SceneActionRequest
from world.scenes.action_serializers import (
    AvailableSceneActionSerializer,
    ConsentResponseSerializer,
    EnhancedSceneActionResultSerializer,
    SceneActionRequestCreateSerializer,
    SceneActionRequestSerializer,
)
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.interaction_permissions import get_account_personas
from world.scenes.models import Persona, Scene


class SceneActionRequestPagination(PageNumberPagination):
    page_size = 20


class SceneActionRequestViewSet(viewsets.ModelViewSet):
    """ViewSet for scene action requests with consent flow."""

    serializer_class = SceneActionRequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SceneActionRequestPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = SceneActionRequestFilter
    http_method_names = ["get", "post"]

    def get_queryset(self) -> QuerySet[SceneActionRequest]:
        from django.db.models import Q  # noqa: PLC0415

        persona_ids = get_account_personas(self.request)
        if not persona_ids:
            return SceneActionRequest.objects.none()
        return (
            SceneActionRequest.objects.filter(
                Q(initiator_persona_id__in=persona_ids) | Q(target_persona_id__in=persona_ids)
            )
            .select_related(
                "initiator_persona",
                "target_persona",
                "scene",
            )
            .order_by("-created_at")
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create a new action request."""
        serializer = SceneActionRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        persona_ids = get_account_personas(request)
        if not persona_ids:
            return Response(
                {"detail": "No personas found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scene_id = serializer.validated_data["scene"]
        initiator_persona_id = serializer.validated_data["initiator_persona"]
        target_persona_id = serializer.validated_data["target_persona"]
        action_key = serializer.validated_data["action_key"]
        difficulty_choice = serializer.validated_data.get(
            "difficulty_choice", DifficultyChoice.NORMAL
        )

        try:
            scene = Scene.objects.get(pk=scene_id, is_active=True)
        except Scene.DoesNotExist:
            return Response(
                {"detail": "Active scene not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Caller must explicitly specify which persona initiates the action.
        if initiator_persona_id not in persona_ids:
            return Response(
                {"detail": "Initiator persona not found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        initiator_persona = get_object_or_404(Persona, pk=initiator_persona_id)

        target_persona = get_object_or_404(Persona, pk=target_persona_id)

        technique = None
        technique_id = serializer.validated_data.get("technique_id")
        if technique_id is not None:
            from world.magic.models import Technique  # noqa: PLC0415

            technique = get_object_or_404(Technique, pk=technique_id)

        action_request = create_action_request(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            action_key=action_key,
            difficulty_choice=difficulty_choice,
            technique=technique,
        )

        return Response(
            SceneActionRequestSerializer(action_request).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=[HTTPMethod.GET], url_path="available")
    def available(self, request: Request) -> Response:
        """Return social actions available to the requesting user's character.

        Resolves the character from the first persona owned by the account,
        then returns all social ActionTemplates with technique enhancement
        options for that character.
        """
        from world.scenes.action_availability import get_available_scene_actions  # noqa: PLC0415
        from world.scenes.interaction_permissions import get_account_roster_entries  # noqa: PLC0415

        roster_entries = get_account_roster_entries(request)
        if not roster_entries:
            return Response([], status=status.HTTP_200_OK)

        character_id = roster_entries[0].character_id
        from evennia.objects.models import ObjectDB  # noqa: PLC0415

        try:
            character = ObjectDB.objects.get(pk=character_id)
        except ObjectDB.DoesNotExist:
            return Response([], status=status.HTTP_200_OK)

        actions = get_available_scene_actions(character=character)
        serializer = AvailableSceneActionSerializer(actions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="respond")
    def respond(self, request: Request, pk: int | None = None) -> Response:
        """Respond to a pending action request (accept/deny)."""
        persona_ids = get_account_personas(request)
        if not persona_ids:
            return Response(
                {"detail": "No personas found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            action_request = SceneActionRequest.objects.get(
                pk=pk,
                target_persona_id__in=persona_ids,
                status=ActionRequestStatus.PENDING,
            )
        except SceneActionRequest.DoesNotExist:
            return Response(
                {"detail": "Pending action request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        consent_serializer = ConsentResponseSerializer(data=request.data)
        consent_serializer.is_valid(raise_exception=True)
        decision = consent_serializer.validated_data["decision"]

        try:
            result = respond_to_action_request(
                action_request=action_request,
                decision=decision,
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action_request.refresh_from_db()
        response_data = SceneActionRequestSerializer(action_request).data
        if result is not None:
            response_data["result"] = EnhancedSceneActionResultSerializer(result).data

        return Response(response_data)
