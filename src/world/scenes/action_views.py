"""ViewSets for scene action requests."""

from __future__ import annotations

from http import HTTPMethod
from typing import Any

from django.db.models import QuerySet
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
    ConsentResponseSerializer,
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

        # Use the first persona the user controls
        initiator_persona = Persona.objects.filter(pk__in=persona_ids).first()
        if initiator_persona is None:
            return Response(
                {"detail": "No persona found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_persona = Persona.objects.get(pk=target_persona_id)
        except Persona.DoesNotExist:
            return Response(
                {"detail": "Target persona not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        action_request = create_action_request(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            action_key=action_key,
            difficulty_choice=difficulty_choice,
        )

        return Response(
            SceneActionRequestSerializer(action_request).data,
            status=status.HTTP_201_CREATED,
        )

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
            main_result = result.action_resolution.main_result
            check_result = main_result.check_result if main_result is not None else None
            response_data["result"] = {
                "action_key": result.action_key,
                "phase": result.action_resolution.current_phase,
                "outcome_name": check_result.outcome_name if check_result is not None else None,
            }

        return Response(response_data)
