"""Web surface for pre-scene capture consent (#3069 sub-item 4).

Read-only list (the account's own pending requests, each carrying a preview of the
poses that would be captured — the requester's own content only, per the ruling's
privacy invariant) plus a ``respond`` action. Mirrors ``SpeakerQueueViewSet``'s shape:
read via list, mutation via one @action endpoint.
"""

from __future__ import annotations

from http import HTTPMethod
from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.scenes.action_constants import ActionRequestStatus
from world.scenes.models import Interaction, PrecaptureConsentRequest
from world.scenes.precapture_services import (
    precapture_candidates_for,
    respond_to_precapture_consent,
)


class PrecapturePreviewInteractionSerializer(serializers.ModelSerializer):
    """One candidate pose in a consent preview — the requester's own content only."""

    persona_name = serializers.CharField(source="persona.name", read_only=True)

    class Meta:
        model = Interaction
        fields = ["id", "persona_name", "content", "mode", "timestamp"]


class PrecaptureConsentRequestSerializer(serializers.ModelSerializer):
    scene_name = serializers.CharField(source="scene.name", read_only=True)
    room_name = serializers.SerializerMethodField()
    candidates = serializers.SerializerMethodField()

    class Meta:
        model = PrecaptureConsentRequest
        fields = [
            "id",
            "scene",
            "scene_name",
            "room_name",
            "status",
            "requested_at",
            "responded_at",
            "candidates",
        ]
        read_only_fields = fields

    def get_room_name(self, obj: PrecaptureConsentRequest) -> str | None:
        location = obj.scene.location
        return location.db_key if location is not None else None

    def get_candidates(self, obj: PrecaptureConsentRequest) -> Any:
        return PrecapturePreviewInteractionSerializer(
            precapture_candidates_for(obj), many=True
        ).data


class RespondPrecaptureConsentRequestSerializer(serializers.Serializer):
    accept = serializers.BooleanField()


class PrecaptureConsentRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """The requesting account's own precapture consent requests."""

    serializer_class = PrecaptureConsentRequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post"]

    def get_queryset(self) -> QuerySet[PrecaptureConsentRequest]:
        # Account-scoped: a request row's `account` IS the requesting account when
        # authenticated — no persona lookup needed (#1219 party identity).
        return (
            PrecaptureConsentRequest.objects.filter(
                account=self.request.user,
                status=ActionRequestStatus.PENDING,
            )
            .select_related("scene", "scene__location")
            .order_by("requested_at")
        )

    @action(detail=True, methods=[HTTPMethod.POST])
    def respond(self, request: Request, pk: int | None = None) -> Response:
        """Accept or decline this consent request.

        Looks up by (pk, account) directly rather than through ``get_queryset`` (which
        is PENDING-only) so a double-submit lands on the "already resolved" 400 below
        instead of a bare 404 — the row still belongs to this account either way.
        """
        consent_request = get_object_or_404(PrecaptureConsentRequest, pk=pk, account=request.user)
        serializer = RespondPrecaptureConsentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if consent_request.status != ActionRequestStatus.PENDING:
            return Response(
                {"detail": "This request has already been resolved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attached = respond_to_precapture_consent(
            consent_request, accept=serializer.validated_data["accept"]
        )
        return Response({"attached_count": attached, "status": consent_request.status})
