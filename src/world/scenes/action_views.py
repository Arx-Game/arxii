"""ViewSets for scene action requests."""

from __future__ import annotations

from http import HTTPMethod
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
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
    CastableTechniqueSerializer,
    ConsentResponseSerializer,
    EnhancedSceneActionResultSerializer,
    SceneActionRequestCreateSerializer,
    SceneActionRequestSerializer,
    TechniqueCastCreateSerializer,
)
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.cast_services import request_technique_cast
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

        strain_commitment = serializer.validated_data.get("strain_commitment", 0) or 0

        action_request = create_action_request(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            action_key=action_key,
            difficulty_choice=difficulty_choice,
            technique=technique,
            strain_commitment=strain_commitment,
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
        except ValueError as _exc:
            return Response(
                {"detail": "Unable to process this action request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action_request.refresh_from_db()
        response_data = SceneActionRequestSerializer(action_request).data
        if result is not None:
            response_data["result"] = EnhancedSceneActionResultSerializer(
                result,
                context={"request": request, "action_request": action_request},
            ).data

        return Response(response_data)

    @action(detail=False, methods=[HTTPMethod.POST], url_path="cast")
    def cast(self, request: Request) -> Response:
        """Submit a standalone technique cast.

        Routes per the consent/combat/immediate matrix:
        - self/room/no-target → resolves immediately (201 with result + power_ledger)
        - benign at another PC → PENDING consent request (201, no result yet)
        - hostile at another PC → seeds/feeds a combat encounter (201 with encounter summary)
        """
        from world.magic.models import Technique  # noqa: PLC0415

        serializer = TechniqueCastCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        persona_ids = get_account_personas(request)
        if not persona_ids:
            return Response(
                {"detail": "No personas found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vd = serializer.validated_data
        scene_id = vd["scene"]
        initiator_persona_id = vd["initiator_persona"]
        technique_id = vd["technique_id"]
        target_persona_id = vd.get("target_persona")
        strain_commitment = vd.get("strain_commitment", 0) or 0

        try:
            scene = Scene.objects.get(pk=scene_id, is_active=True)
        except Scene.DoesNotExist:
            return Response(
                {"detail": "Active scene not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if initiator_persona_id not in persona_ids:
            return Response(
                {"detail": "Initiator persona not found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        initiator_persona = get_object_or_404(Persona, pk=initiator_persona_id)

        target_persona: Persona | None = None
        if target_persona_id is not None:
            target_persona = get_object_or_404(Persona, pk=target_persona_id)

        technique = get_object_or_404(Technique, pk=technique_id)

        try:
            cast_result = request_technique_cast(
                scene=scene,
                initiator_persona=initiator_persona,
                target_persona=target_persona,
                technique=technique,
                strain_commitment=strain_commitment,
            )
        except DjangoValidationError as exc:
            messages = exc.messages if hasattr(exc, "messages") else ["Unable to process cast."]
            return Response(
                {"detail": messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_data = SceneActionRequestSerializer(cast_result.request).data

        if cast_result.result is not None:
            response_data["result"] = EnhancedSceneActionResultSerializer(
                cast_result.result,
                context={"request": request},
            ).data

        if cast_result.encounter is not None:
            response_data["encounter"] = {
                "id": cast_result.encounter.pk,
                "status": cast_result.encounter.status,
            }

        if cast_result.outcome_interaction is not None:
            response_data["outcome_interaction"] = cast_result.outcome_interaction.pk

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=[HTTPMethod.GET], url_path="castable-techniques")
    def castable_techniques(self, request: Request) -> Response:
        """List techniques the given persona can cast standalone.

        Requires ?initiator_persona=<id> query param. Returns only techniques
        with an action_template (castable standalone) known by that character.
        """
        from world.magic.models.techniques import CharacterTechnique  # noqa: PLC0415

        initiator_persona_id_str = request.query_params.get("initiator_persona")  # noqa: USE_FILTERSET
        if not initiator_persona_id_str:
            return Response(
                {"detail": "initiator_persona query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            initiator_persona_id = int(initiator_persona_id_str)
        except (TypeError, ValueError):
            return Response(
                {"detail": "initiator_persona must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        persona_ids = get_account_personas(request)
        if initiator_persona_id not in persona_ids:
            return Response(
                {"detail": "Initiator persona not found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        initiator_persona = get_object_or_404(Persona, pk=initiator_persona_id)
        sheet_id = initiator_persona.character_sheet_id

        char_techniques = (
            CharacterTechnique.objects.filter(
                character_id=sheet_id,
                technique__action_template__isnull=False,
            )
            .select_related("technique", "technique__action_template", "technique__effect_type")
            .order_by("technique__name")
        )

        techniques = [ct.technique for ct in char_techniques]
        return Response(CastableTechniqueSerializer(techniques, many=True).data)
