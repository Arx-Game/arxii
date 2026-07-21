"""Speaker queue web ViewSet — read + action endpoints (#2356).

Mirrors ``PlaceViewSet``: read via list, mutations via @action endpoints
that dispatch through the same Actions telnet uses.
"""

from __future__ import annotations

from http import HTTPMethod
from typing import Any

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.scenes.interaction_permissions import get_account_personas
from world.scenes.models import Persona
from world.scenes.speaker_queue_models import SpeakerQueue, SpeakerQueueEntry
from world.scenes.speaker_queue_services import get_active_queue, queue_entries

_NO_CHARACTER_FOUND = "No character found."


class SpeakerQueueEntrySerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True)

    class Meta:
        model = SpeakerQueueEntry
        fields = ["id", "persona", "persona_name", "position", "joined_at"]
        read_only_fields = ["id", "position", "joined_at"]


class SpeakerQueueSerializer(serializers.ModelSerializer):
    entries = serializers.SerializerMethodField()
    opened_by_name = serializers.CharField(source="opened_by.name", read_only=True)

    class Meta:
        model = SpeakerQueue
        fields = [
            "id",
            "room",
            "scene",
            "is_active",
            "opened_by",
            "opened_by_name",
            "opened_at",
            "closed_at",
            "entries",
        ]
        read_only_fields = ["id", "opened_at", "closed_at"]

    def get_entries(self, obj: SpeakerQueue) -> Any:
        # No Prefetch(to_attr=...) fallback here: nothing sets one, and adding it
        # onto a SharedMemoryModel would leak prefetched rows across requests —
        # pass batched entries via serializer context if list query counts ever
        # need trimming.
        return SpeakerQueueEntrySerializer(queue_entries(obj), many=True).data


class SpeakerQueueViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet with action endpoints for speaker queue mutations."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = SpeakerQueueSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["room", "is_active"]
    http_method_names = ["get", "post"]

    def get_queryset(self) -> QuerySet[SpeakerQueue]:
        return SpeakerQueue.objects.filter(is_active=True).order_by("-opened_at")

    @action(detail=False, methods=[HTTPMethod.POST], url_path="open")
    def open_queue(self, request: Request) -> Response:
        """Open a speaker queue in the caller's room."""
        from actions.definitions.speaker_queue import OpenSpeakerQueueAction  # noqa: PLC0415

        character = self._get_character(request)
        if character is None:
            return Response(
                {"detail": "No character found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = OpenSpeakerQueueAction().run(actor=character)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        queue = get_active_queue(character.location)
        return Response(
            SpeakerQueueSerializer(queue).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=[HTTPMethod.POST], url_path="close")
    def close_queue(self, request: Request, pk: int | None = None) -> Response:
        from actions.definitions.speaker_queue import CloseSpeakerQueueAction  # noqa: PLC0415

        character = self._get_character(request)
        if character is None:
            return Response(
                {"detail": _NO_CHARACTER_FOUND},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = CloseSpeakerQueueAction().run(actor=character)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="join")
    def join_queue(self, request: Request, pk: int | None = None) -> Response:
        from actions.definitions.speaker_queue import JoinSpeakerQueueAction  # noqa: PLC0415

        character = self._get_character(request)
        if character is None:
            return Response(
                {"detail": _NO_CHARACTER_FOUND},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = JoinSpeakerQueueAction().run(actor=character)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        queue = get_active_queue(character.location)
        return Response(SpeakerQueueSerializer(queue).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="leave")
    def leave_queue(self, request: Request, pk: int | None = None) -> Response:
        from actions.definitions.speaker_queue import LeaveSpeakerQueueAction  # noqa: PLC0415

        character = self._get_character(request)
        if character is None:
            return Response(
                {"detail": _NO_CHARACTER_FOUND},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = LeaveSpeakerQueueAction().run(actor=character)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="advance")
    def advance_queue(self, request: Request, pk: int | None = None) -> Response:
        from actions.definitions.speaker_queue import AdvanceSpeakerQueueAction  # noqa: PLC0415

        character = self._get_character(request)
        if character is None:
            return Response(
                {"detail": _NO_CHARACTER_FOUND},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = AdvanceSpeakerQueueAction().run(actor=character)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        queue = get_active_queue(character.location)
        return Response(SpeakerQueueSerializer(queue).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="skip")
    def skip_speaker(self, request: Request, pk: int | None = None) -> Response:
        from actions.definitions.speaker_queue import SkipSpeakerAction  # noqa: PLC0415

        target_name = request.data.get("target_name", "")
        if not target_name:
            return Response(
                {"detail": "Skip whom?"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        character = self._get_character(request)
        if character is None:
            return Response(
                {"detail": _NO_CHARACTER_FOUND},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = SkipSpeakerAction().run(actor=character, target_name=target_name)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        queue = get_active_queue(character.location)
        return Response(SpeakerQueueSerializer(queue).data, status=status.HTTP_200_OK)

    def _get_character(self, request: Request) -> Any:
        """Resolve the caller's character from their account personas."""
        persona_ids = get_account_personas(request)
        persona = (
            Persona.objects.filter(pk__in=persona_ids)
            .select_related("character_sheet__character")
            .first()
        )
        if persona is None:
            return None
        return persona.character_sheet.character
