"""ViewSets for scene action requests."""

from __future__ import annotations

from http import HTTPMethod
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from actions.registry import get_action
from actions.types import TargetType
from world.conditions.constants import TARGET_EFFECT_ALTERATION, TARGET_EFFECT_CONDITION
from world.magic.exceptions import MagicError
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_filters import SceneActionRequestFilter, SceneActionTargetFilter
from world.scenes.action_models import SceneActionRequest, SceneActionTarget
from world.scenes.action_serializers import (
    CastableTechniqueSerializer,
    ConsentResponseSerializer,
    EnhancedSceneActionResultSerializer,
    SceneActionRequestCreateSerializer,
    SceneActionRequestSerializer,
    SceneActionTargetSerializer,
    TechniqueCastCreateSerializer,
)
from world.scenes.action_services import (
    create_action_request,
    respond_to_action_request,
    respond_to_action_target,
)
from world.scenes.cast_services import request_technique_cast
from world.scenes.interaction_permissions import get_account_personas
from world.scenes.models import Persona, Scene

# Repeated API error detail strings. Centralized to avoid the duplicated-literal
# SonarCloud smell (python:S1192).
_NO_PERSONAS_DETAIL = "No personas found for your account."
_INITIATOR_NOT_FOUND_DETAIL = "Initiator persona not found for your account."

# Action key for the treat-condition consent flow (matches TreatConditionAction.key).
TREAT_CONDITION_KEY = "treat_condition"


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
            # perf: technique, technique__effect_type, and
            # target_persona__character_sheet must stay in select_related —
            # SceneActionRequestSerializer.get_combat_risk_level walks them per row.
            .select_related(
                "initiator_persona",
                "target_persona",
                "target_persona__character_sheet",
                "scene",
                "technique",
                "technique__effect_type",
            )
            .order_by("-created_at")
        )

    @staticmethod
    def _validate_cardinality(action_key: str, target_ids: list[int]) -> None:
        """Raise DRFValidationError if target_ids conflict with the action's target_type."""
        registered_action = get_action(action_key)
        cardinality = (
            registered_action.target_type if registered_action is not None else TargetType.SINGLE
        )
        if cardinality == TargetType.SINGLE and len(target_ids) > 1:
            raise DRFValidationError(
                {"target_persona_ids": "This action targets a single persona."}
            )
        if cardinality in (TargetType.AREA, TargetType.FILTERED_GROUP) and not target_ids:
            raise DRFValidationError(
                {"target_persona_ids": "This action requires at least one target."}
            )
        if cardinality == TargetType.SELF and target_ids:
            raise DRFValidationError({"target_persona_ids": "This action targets the caster only."})

    @staticmethod
    def _resolve_delivery_receivers(receiver_ids: list[int]) -> tuple[list[Persona], bool]:
        """Return (resolved_personas, all_found). ``all_found`` is False if any id is missing."""
        if not receiver_ids:
            return [], True
        delivery_receivers = list(Persona.objects.filter(pk__in=receiver_ids))
        return delivery_receivers, len(delivery_receivers) == len(set(receiver_ids))

    @staticmethod
    def _reject_treatment_fields_for_non_treat(
        action_key: str, serializer: SceneActionRequestCreateSerializer
    ) -> None:
        """Reject treatment-only fields submitted for a non-treat_condition action (#1486).

        Treatment fields are only meaningful for treat_condition. Rejecting all four up front lets
        the create path assume ``treatment_id`` implies treat_condition; previously only
        ``treatment_id`` was rejected and the other three were silently ignored.
        """
        if action_key == TREAT_CONDITION_KEY:
            return
        if any(
            v is not None
            for v in (
                serializer.validated_data.get("treatment_id"),
                serializer.validated_data.get("target_condition_instance_id"),
                serializer.validated_data.get("target_pending_alteration_id"),
                serializer.validated_data.get("bond_thread_id"),
            )
        ):
            raise DRFValidationError(
                {"treatment_fields": "Treatment fields are only valid for treat_condition."}
            )

    @staticmethod
    def _resolve_treatment_target_effect(
        serializer: SceneActionRequestCreateSerializer,
    ) -> tuple[Any, str]:
        """Resolve the single treat_condition target effect (condition XOR alteration) (#1486)."""
        one_effect_error = DRFValidationError(
            {"target_effect": "Specify exactly one target effect (condition or alteration)."}
        )
        condition_instance_id = serializer.validated_data.get("target_condition_instance_id")
        pending_alteration_id = serializer.validated_data.get("target_pending_alteration_id")
        if condition_instance_id is not None and pending_alteration_id is not None:
            raise one_effect_error
        if condition_instance_id is not None:
            from world.conditions.models import ConditionInstance  # noqa: PLC0415

            target_effect = get_object_or_404(ConditionInstance, pk=condition_instance_id)
            return target_effect, TARGET_EFFECT_CONDITION
        if pending_alteration_id is not None:
            from world.magic.models import PendingAlteration  # noqa: PLC0415

            target_effect = get_object_or_404(PendingAlteration, pk=pending_alteration_id)
            return target_effect, TARGET_EFFECT_ALTERATION
        raise one_effect_error

    def _resolve_treatment(
        self,
        serializer: SceneActionRequestCreateSerializer,
        *,
        action_key: str,
        initiator_persona: Persona,
        target_persona: Persona | None,
        scene: Scene,
    ) -> tuple[Any, Any, str | None, dict[str, Any] | None]:
        """Validate & resolve the treat_condition treatment, target effect, and matched candidate.

        Returns ``(treatment, target_effect, target_effect_type, matched_candidate)``; all ``None``
        for non-treat actions. Re-runs ``get_treatment_candidates`` and requires the submitted pair
        to match one candidate by pk, so every scene/engagement/bond gate stays in the service and
        a client cannot fabricate an arbitrary treatment_id + target pair (#1486).
        """
        if action_key != TREAT_CONDITION_KEY:
            return None, None, None, None

        treatment_id = serializer.validated_data.get("treatment_id")
        if treatment_id is None:
            raise DRFValidationError({"treatment_id": "treat_condition requires a treatment_id."})
        # treat_condition is a heal-another flow: it always targets a single other persona.
        # Cardinality allows 0 targets for SINGLE actions, so guard explicitly.
        if target_persona is None:
            raise DRFValidationError(
                {"target_persona": "treat_condition requires a target persona."}
            )

        target_effect, target_effect_type = self._resolve_treatment_target_effect(serializer)

        from world.conditions.models import TreatmentTemplate  # noqa: PLC0415
        from world.conditions.services import get_treatment_candidates  # noqa: PLC0415

        treatment = get_object_or_404(TreatmentTemplate, pk=treatment_id)
        candidates = get_treatment_candidates(
            initiator_persona.character_sheet, target_persona.character_sheet, scene
        )
        matched_candidate = next(
            (
                c
                for c in candidates
                if c["treatment"].pk == treatment.pk
                and c["target_effect"].pk == target_effect.pk
                and c["target_effect_type"] == target_effect_type
            ),
            None,
        )
        if matched_candidate is None:
            raise DRFValidationError(
                {"treatment": "That treatment is not available for this target in this scene."}
            )
        return treatment, target_effect, target_effect_type, matched_candidate

    @staticmethod
    def _apply_treatment_fks(
        action_request: SceneActionRequest,
        *,
        treatment: Any,
        target_effect: Any,
        target_effect_type: str | None,
        matched_candidate: dict[str, Any],
    ) -> None:
        """Mirror the telnet treat command's FK-setting on a freshly created request (#1486).

        Sets treatment, the matching target effect, and the matched candidate's bond_thread (NOT a
        client-supplied id — the discovery query already selected the valid anchored thread).
        """
        action_request.treatment = treatment
        if target_effect_type == TARGET_EFFECT_CONDITION:
            action_request.target_condition_instance = target_effect
        else:
            action_request.target_pending_alteration = target_effect
        action_request.thread_used = matched_candidate["bond_thread"]
        action_request.save(
            update_fields=[
                "treatment",
                "target_condition_instance",
                "target_pending_alteration",
                "thread_used",
            ]
        )

    @extend_schema(
        request=SceneActionRequestCreateSerializer, responses=SceneActionRequestSerializer
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create a new action request."""
        serializer = SceneActionRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        persona_ids = get_account_personas(request)
        if not persona_ids:
            return Response(
                {"detail": _NO_PERSONAS_DETAIL},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scene_id = serializer.validated_data["scene"]
        initiator_persona_id = serializer.validated_data["initiator_persona"]
        action_key = serializer.validated_data["action_key"]
        target_ids: list[int] = serializer.validated_data["target_ids"]
        effort_level: str = serializer.validated_data["effort_level"]

        self._validate_cardinality(action_key, target_ids)
        self._reject_treatment_fields_for_non_treat(action_key, serializer)

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
                {"detail": _INITIATOR_NOT_FOUND_DETAIL},
                status=status.HTTP_400_BAD_REQUEST,
            )
        initiator_persona = get_object_or_404(Persona, pk=initiator_persona_id)

        primary_id = target_ids[0] if target_ids else None
        target_persona = (
            get_object_or_404(Persona, pk=primary_id) if primary_id is not None else None
        )
        additional = [get_object_or_404(Persona, pk=pk) for pk in target_ids[1:]]

        technique = None
        technique_id = serializer.validated_data.get("technique_id")
        if technique_id is not None:
            from world.magic.models import Technique  # noqa: PLC0415

            technique = get_object_or_404(Technique, pk=technique_id)

        strain_commitment = serializer.validated_data.get("strain_commitment", 0) or 0

        delivery = serializer.validated_data.get("delivery", "")
        receiver_ids = serializer.validated_data.get("delivery_receiver_ids", [])
        delivery_receivers, all_found = self._resolve_delivery_receivers(receiver_ids)
        if not all_found:
            return Response(
                {"detail": "One or more delivery receivers not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        treatment, target_effect, target_effect_type, matched_candidate = self._resolve_treatment(
            serializer,
            action_key=action_key,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            scene=scene,
        )

        try:
            action_request = create_action_request(
                scene=scene,
                initiator_persona=initiator_persona,
                target_persona=target_persona,
                action_key=action_key,
                effort_level=effort_level,
                technique=technique,
                strain_commitment=strain_commitment,
                delivery=delivery,
                delivery_receivers=delivery_receivers,
                additional_target_personas=additional,
            )
        except DjangoValidationError as exc:
            messages = exc.messages if hasattr(exc, "messages") else ["Unable to create action."]
            return Response(
                {"detail": messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Mirror the telnet treat command's FK-setting (commands/conditions.py).
        if action_key == TREAT_CONDITION_KEY and matched_candidate is not None:
            self._apply_treatment_fks(
                action_request,
                treatment=treatment,
                target_effect=target_effect,
                target_effect_type=target_effect_type,
                matched_candidate=matched_candidate,
            )

        return Response(
            SceneActionRequestSerializer(action_request).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=ConsentResponseSerializer)
    @action(detail=True, methods=[HTTPMethod.POST], url_path="respond")
    def respond(self, request: Request, pk: int | None = None) -> Response:  # noqa: PLR0911
        """Respond to a pending action request (accept/deny).

        When ``target_persona_id`` is present in the payload the caller is
        consenting on behalf of an additional-target row (SceneActionTarget).
        The primary-request status is NOT checked in that branch — the primary
        may already be RESOLVED/DENIED while additional rows are still PENDING.

        When ``target_persona_id`` is absent, the existing primary-target path
        is used unchanged.
        """
        persona_ids = get_account_personas(request)
        if not persona_ids:
            return Response(
                {"detail": _NO_PERSONAS_DETAIL},
                status=status.HTTP_400_BAD_REQUEST,
            )

        consent_serializer = ConsentResponseSerializer(data=request.data)
        consent_serializer.is_valid(raise_exception=True)
        decision = consent_serializer.validated_data["decision"]
        target_persona_id = consent_serializer.validated_data.get("target_persona_id")
        difficulty = consent_serializer.validated_data.get("difficulty")
        resist_effort = consent_serializer.validated_data.get("resist_effort", "")

        if target_persona_id is not None:
            # Per-target consent path: look up the additional-target row directly.
            # Do not gate on the request's own status (primary may be terminal).
            action_target = get_object_or_404(
                SceneActionTarget,
                action_request_id=pk,
                target_persona_id=target_persona_id,
            )
            if action_target.target_persona_id not in persona_ids:
                return Response(
                    {"detail": "You do not control the targeted persona."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            try:
                result = respond_to_action_target(
                    action_target=action_target,
                    decision=decision,
                    difficulty=difficulty,
                    resist_effort=resist_effort,
                )
            except ValueError:
                return Response(
                    {"detail": "Unable to process this action request."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            action_target.refresh_from_db()
            response_data: dict = {
                "action_target_id": action_target.pk,
                "action_request_id": action_target.action_request_id,
                "target_persona_id": action_target.target_persona_id,
                "status": action_target.status,
            }
            if result is not None:
                response_data["result"] = EnhancedSceneActionResultSerializer(
                    result,
                    context={"request": request, "action_request": action_target.action_request},
                ).data
            return Response(response_data)

        # Primary-target path — unchanged.
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

        try:
            result = respond_to_action_request(
                action_request=action_request,
                decision=decision,
                difficulty=difficulty,
                resist_effort=resist_effort,
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

    @staticmethod
    def _resolve_supplied_personas(
        target_persona_ids: list[int] | None,
    ) -> tuple[list[Persona] | None, bool]:
        """Resolve FILTERED_GROUP picker ids to Persona objects.

        Returns ``(resolved, all_found)``. ``resolved`` is None when no ids supplied.
        """
        if target_persona_ids is None:
            return None, True
        supplied = list(Persona.objects.filter(pk__in=target_persona_ids))
        return supplied, len(supplied) == len(set(target_persona_ids))

    @extend_schema(
        request=TechniqueCastCreateSerializer,
        responses={201: SceneActionRequestSerializer},
    )
    @action(detail=False, methods=[HTTPMethod.POST], url_path="cast")
    def cast(self, request: Request) -> Response:  # noqa: C901, PLR0911
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
                {"detail": _NO_PERSONAS_DETAIL},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vd = serializer.validated_data
        scene_id = vd["scene"]
        initiator_persona_id = vd["initiator_persona"]
        technique_id = vd["technique_id"]
        target_persona_id = vd.get("target_persona")
        strain_commitment = vd.get("strain_commitment", 0) or 0

        cast_pull = None
        pull_data = vd.get("pull")
        if pull_data:
            from world.magic.types.pull import CastPullDeclaration  # noqa: PLC0415

            cast_pull = CastPullDeclaration(
                resonance=pull_data["resonance"],
                tier=pull_data["tier"],
                threads=tuple(pull_data["threads"]),
            )

        try:
            scene = Scene.objects.get(pk=scene_id, is_active=True)
        except Scene.DoesNotExist:
            return Response(
                {"detail": "Active scene not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if initiator_persona_id not in persona_ids:
            return Response(
                {"detail": _INITIATOR_NOT_FOUND_DETAIL},
                status=status.HTTP_400_BAD_REQUEST,
            )
        initiator_persona = get_object_or_404(Persona, pk=initiator_persona_id)

        target_persona: Persona | None = None
        if target_persona_id is not None:
            target_persona = get_object_or_404(Persona, pk=target_persona_id)

        # Resolve the FILTERED_GROUP picker list, if provided.
        raw_target_ids: list[int] | None = vd.get("target_persona_ids") or None
        supplied_personas, all_found = self._resolve_supplied_personas(raw_target_ids)
        if not all_found:
            return Response(
                {"detail": "One or more target personas not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        technique = get_object_or_404(Technique, pk=technique_id)

        use_base_form: bool = vd.get("use_base_form", False)

        try:
            cast_result = request_technique_cast(
                scene=scene,
                initiator_persona=initiator_persona,
                target_persona=target_persona,
                technique=technique,
                strain_commitment=strain_commitment,
                cast_pull=cast_pull,
                supplied_personas=supplied_personas,
                use_base_form=use_base_form,
            )
        except DjangoValidationError as exc:
            messages = exc.messages if hasattr(exc, "messages") else ["Unable to process cast."]
            return Response(
                {"detail": messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except MagicError as exc:
            return Response(
                {"detail": exc.user_message},
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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "initiator_persona",
                type=int,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Persona id (owned by the requester) to list castable techniques for.",
            ),
        ],
        responses={200: CastableTechniqueSerializer(many=True)},
    )
    @action(
        detail=False,
        methods=[HTTPMethod.GET],
        url_path="castable-techniques",
        pagination_class=None,
    )
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
                {"detail": _INITIATOR_NOT_FOUND_DETAIL},
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


class SceneActionTargetViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only listing of a persona's pending additional-target consent rows (#1177)."""

    serializer_class = SceneActionTargetSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SceneActionRequestPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = SceneActionTargetFilter
    http_method_names = ["get"]

    def get_queryset(self) -> QuerySet[SceneActionTarget]:
        persona_ids = get_account_personas(self.request)
        if not persona_ids:
            return SceneActionTarget.objects.none()
        return (
            SceneActionTarget.objects.filter(target_persona_id__in=persona_ids)
            .select_related(
                "action_request",
                "action_request__initiator_persona",
                "action_request__scene",
                "action_request__technique",
                "action_request__technique__effect_type",
                "target_persona",
                "target_persona__character_sheet",
            )
            .order_by("-action_request__created_at", "id")
        )
