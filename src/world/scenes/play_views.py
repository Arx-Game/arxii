"""Authorized reader contracts for the narrative play workspace."""

from __future__ import annotations

import base64
from datetime import date, timedelta
import json
from typing import Any
import uuid

from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.scenes.interaction_filters import InteractionFilter
from world.scenes.interaction_permissions import get_account_personas
from world.scenes.interaction_serializers import InteractionListSerializer
from world.scenes.interaction_views import InteractionViewSet
from world.scenes.models import Interaction, PoseSubmission

SEARCH_MIN_LENGTH = 2
SEARCH_MAX_LENGTH = 200
DATE_ONLY_LENGTH = 10
WHISPER_MODE = "whisper"
OOC_MODES = frozenset({"ooc", "system"})
TEMPORARY_AVAILABILITY = "temporary"
RETAINED_AVAILABILITY = "retained"
ROOM_KEY = "room"
SCENE_OOC_KIND = "scene_ooc"
CHANNEL_KIND = "channel"
TABLETALK_MODE = "tt"


def _row_key(row: dict[str, Any]) -> tuple[str, int]:
    """Return the stable pose boundary for either a pose or summary row."""
    pose = row.get("latestVisiblePose") or row.get("pose") or row
    return str(pose["timestamp"]), int(pose["id"])


def _cursor(row: dict[str, Any]) -> str:
    """Encode the deterministic timestamp/id boundary without exposing query state."""
    value = json.dumps(list(_row_key(row)), separators=(",", ":"))
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _page(results: list[dict[str, Any]], limit: int, request: Request) -> Response:
    """Return an ascending, cursor-addressable page envelope."""
    before_token = request.query_params.get("before")
    after_token = request.query_params.get("after")
    start_index = max(0, len(results) - limit)
    end_index = len(results)
    if before_token or after_token:
        token = before_token or after_token
        if token is None:
            return Response({"detail": "Invalid history cursor."}, status=400)
        try:
            padded = token + "=" * (-len(token) % 4)
            timestamp, row_id = json.loads(base64.urlsafe_b64decode(padded).decode())
            boundary = (str(timestamp), int(row_id))
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            return Response({"detail": "Invalid history cursor."}, status=400)
        keys = [_row_key(row) for row in results]
        if after_token:
            start_index = next(
                (index for index, key in enumerate(keys) if key > boundary), len(results)
            )
        else:
            end_index = next(
                (index for index, key in enumerate(keys) if key >= boundary), len(results)
            )
            start_index = max(0, end_index - limit)
    page = results[start_index : start_index + limit]
    return Response(
        {
            "results": page,
            "before": _cursor(page[0]) if start_index > 0 and page else None,
            "after": _cursor(page[-1]) if start_index + len(page) < end_index and page else None,
            "snapshot": timezone.now().isoformat(),
        }
    )


def _queryset(request: Request) -> tuple[QuerySet[Interaction], dict[str, Any]]:
    """Build the canonical visible interaction queryset and serializer context.

    The play endpoints intentionally reuse ``InteractionViewSet``. This keeps
    masking, language comprehension, block/mute rules, and private-party
    visibility identical to the existing scene feed.
    """
    view = InteractionViewSet()
    view.request = request
    view.args = ()
    view.kwargs = {}
    view.format_kwarg = None
    queryset = view.get_queryset()
    # ``from`` is the UI spelling for an explicit older-history lower bound.
    since = request.query_params.get("from")
    until = request.query_params.get("to") or request.query_params.get("until")
    if since:
        queryset = queryset.filter(timestamp__gte=since)
    if until:
        # Date-only UI bounds include the whole selected day rather than only
        # midnight. Datetime bounds remain exact and timezone-aware upstream.
        if len(until) == DATE_ONLY_LENGTH:
            try:
                exclusive_until = (date.fromisoformat(until) + timedelta(days=1)).isoformat()
            except ValueError:
                queryset = queryset.filter(timestamp__lte=until)
            else:
                queryset = queryset.filter(timestamp__lt=exclusive_until)
        else:
            queryset = queryset.filter(timestamp__lte=until)
    queryset = InteractionFilter(request.query_params, queryset=queryset).qs
    conversation = request.query_params.get("conversation")
    if conversation and conversation.startswith("scene:"):
        queryset = queryset.filter(scene_id=conversation.removeprefix("scene:"))
    elif conversation == ROOM_KEY:
        queryset = queryset.filter(scene__isnull=True)
    return queryset.order_by("timestamp", "id"), view.get_serializer_context()


def _ref(row: dict[str, Any]) -> dict[str, str]:
    return {"id": str(row["id"]), "timestamp": row["timestamp"]}


def _conversation(row: dict[str, Any]) -> dict[str, str]:
    """Build a stable non-sensitive conversation reference from serialized context."""
    mode = str(row.get("mode") or "").lower()
    receivers = row.get("receiver_persona_ids") or []
    if mode == WHISPER_MODE and receivers:
        speaker = row.get("persona", {}).get("id")
        participants = [speaker, *receivers] if speaker is not None else receivers
        return {
            "kind": WHISPER_MODE,
            "key": "whisper:" + ",".join(str(i) for i in sorted(set(participants))),
        }
    place = row.get("place")
    if place is not None:
        return {"kind": "place", "key": f"place:{place}"}
    if mode in OOC_MODES:
        return {"kind": SCENE_OOC_KIND, "key": mode}
    if mode == TABLETALK_MODE:
        return {"kind": CHANNEL_KIND, "key": "tt"}
    scene = row.get("scene")
    if scene is not None:
        return {"kind": "room", "key": f"scene:{scene}"}
    return {"kind": "room", "key": ROOM_KEY}


def _rows(request: Request) -> tuple[list[dict[str, Any]], QuerySet[Interaction]]:
    queryset, context = _queryset(request)
    serialized = InteractionListSerializer(queryset, many=True, context=context).data
    return list(serialized), queryset


class PlayConversationsView(APIView):
    """GET authorized conversation summaries for the play navigator."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        rows, _ = _rows(request)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            ref = _conversation(row)
            grouped.setdefault(f"{ref['kind']}:{ref['key']}", []).append(row)
        results = []
        for group in grouped.values():
            first, latest = group[0], group[-1]
            ref = _conversation(first)
            scene = first.get("scene")
            results.append(
                {
                    "ref": ref,
                    "title": f"Scene {scene}" if scene is not None else "General conversation",
                    "availability": RETAINED_AVAILABILITY,
                    "canRead": True,
                    "canSend": False,
                    "sceneId": str(scene) if scene is not None else None,
                    "latestVisiblePose": _ref(latest),
                    "unread": 0,
                    "directUnread": 0,
                }
            )
        results.sort(key=lambda item: _row_key(item))
        return _page(results, 30, request)


class PlayPosesView(APIView):
    """GET authorized poses using the existing enriched interaction DTO."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        rows, _ = _rows(request)
        return _page(rows, 100, request)


class PlayContextView(APIView):
    """GET a small authorized context window around a retained pose."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        pose_id = request.query_params.get("id")  # noqa: USE_FILTERSET
        pose_timestamp = request.query_params.get("timestamp")  # noqa: USE_FILTERSET
        conversation = request.query_params.get("conversation")  # noqa: USE_FILTERSET
        rows, _ = _rows(request)
        if conversation:
            rows = [row for row in rows if _conversation(row)["key"] == conversation]
        if not pose_id:
            return Response({"detail": "A pose reference is required."}, status=400)
        for index, row in enumerate(rows):
            if str(row["id"]) != pose_id:
                continue
            if pose_timestamp and str(row["timestamp"]) != pose_timestamp:
                continue
            return Response(
                {"results": rows[max(0, index - 25) : index + 26], "threadId": row.get("thread_id")}
            )
        # Do not distinguish an unauthorized reference from a missing one.
        return Response({"detail": "This pose is no longer available."}, status=404)


class PoseSubmissionDetailView(APIView):
    """GET whether a submitted pose landed, by client_request_id (#3760).

    Writer-only: scoped to the requesting account's own personas via
    ``get_account_personas`` -- the same account-scoping seam
    ``InteractionViewSet`` uses. A non-owner's lookup 404s rather than
    403ing: a resend attempt is not proof of authorship, and a 403 would
    still confirm the row exists.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, client_request_id: uuid.UUID) -> Response:
        persona_ids = get_account_personas(request)
        submission = (
            PoseSubmission.objects.filter(
                persona_id__in=persona_ids,
                client_request_id=client_request_id,
            )
            .select_related("interaction")
            .first()
        )
        if submission is None:
            return Response({"detail": "Submission not found."}, status=404)
        return Response(
            {
                "interaction_id": submission.interaction_id,
                # Every row this endpoint can return already represents an
                # accepted, persisted submission -- a lookup never creates
                # one, so a found row is always a replay from the caller's
                # perspective.
                "replayed": True,
            }
        )


class PlaySearchView(APIView):
    """Search only viewer-rendered, authorized interaction text."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        query = request.query_params.get("q", "").strip()  # noqa: USE_FILTERSET
        if not SEARCH_MIN_LENGTH <= len(query) <= SEARCH_MAX_LENGTH:
            return Response(
                {"detail": "Search text must be between 2 and 200 characters."}, status=400
            )
        rows, _ = _rows(request)
        folded = query.casefold()
        results = []
        for row in rows:
            content = str(row.get("content") or "")
            if folded not in content.casefold():
                continue
            start = max(0, content.casefold().find(folded) - 80)
            excerpt = content[start : start + 200]
            results.append(
                {
                    "pose": _ref(row),
                    "conversation": _conversation(row),
                    "title": row["persona"]["name"],
                    "excerpt": excerpt,
                    "availability": RETAINED_AVAILABILITY,
                }
            )
        return _page(results, 30, request)
