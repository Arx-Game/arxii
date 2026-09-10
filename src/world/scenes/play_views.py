"""Authorized reader contracts for the narrative play workspace."""

from __future__ import annotations

import base64
from datetime import date, datetime, timedelta
import json
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.scenes.interaction_filters import InteractionFilter
from world.scenes.interaction_serializers import InteractionListSerializer
from world.scenes.interaction_views import InteractionViewSet
from world.scenes.models import Interaction

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


def _same_instant(recorded: Any, requested: str) -> bool:
    """Compare a served row timestamp against a client-supplied one by value.

    The served value is DRF's ISO-8601 rendering (``Z`` suffix for UTC); a
    caller round-tripping a Python ``datetime.isoformat()`` string instead
    sends the ``+00:00`` spelling of the same instant. Raw string equality
    spuriously rejects that match, so parse both sides before comparing.
    Falls back to string equality for a value neither side can parse.
    """
    try:
        return datetime.fromisoformat(str(recorded)) == datetime.fromisoformat(requested)
    except ValueError:
        return str(recorded) == requested


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
            if pose_timestamp and not _same_instant(row["timestamp"], pose_timestamp):
                continue
            start = max(0, index - 25)
            end = index + 26
            window = rows[start:end]
            return Response(
                {
                    "results": window,
                    "threadId": row.get("thread_id"),
                    "before": _cursor(window[0]) if start > 0 and window else None,
                    "after": _cursor(window[-1]) if end < len(rows) and window else None,
                }
            )
        # Do not distinguish an unauthorized reference from a missing one.
        return Response({"detail": "This pose is no longer available."}, status=404)


class PlaySearchView(APIView):
    """Search only viewer-rendered, authorized interaction text, bounded by
    conversation/kind/date so the comprehension-aware match never scans
    unbounded history (#3759).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        query = request.query_params.get("q", "").strip()  # noqa: USE_FILTERSET
        if not SEARCH_MIN_LENGTH <= len(query) <= SEARCH_MAX_LENGTH:
            return Response(
                {"detail": "Search text must be between 2 and 200 characters."}, status=400
            )
        has_bound = any(
            request.query_params.get(key)  # noqa: USE_FILTERSET
            for key in ("conversation", "kind", "from", "to", "until", "participant")
        )
        if not has_bound:
            return Response(
                {"detail": "Search requires a conversation, kind, participant, or date bound."},
                status=400,
            )
        rows, _ = _rows(request)
        conversation = request.query_params.get("conversation")  # noqa: USE_FILTERSET
        if conversation:
            rows = [row for row in rows if _conversation(row)["key"] == conversation]
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


class PlayThreadsView(APIView):
    """GET server-grouped, paginated thread summaries for one conversation."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        conversation = request.query_params.get("conversation")  # noqa: USE_FILTERSET
        rows, _ = _rows(request)
        if conversation:
            rows = [row for row in rows if _conversation(row)["key"] == conversation]
        read_ids: set[int] = set()
        if request.user.is_authenticated and rows:
            from world.scenes.read_state_services import has_read  # noqa: PLC0415

            read_ids = has_read(
                account=request.user,  # type: ignore[invalid-argument-type]
                interaction_ids=[row["id"] for row in rows],
            )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = row.get("thread_id") or f"legacy:{row['id']}"
            grouped.setdefault(key, []).append(row)
        results = []
        for key, members in grouped.items():
            root, latest = members[0], members[-1]
            unread = sum(1 for m in members if int(m["id"]) not in read_ids)
            results.append(
                {
                    "id": key,
                    "conversation": _conversation(root),
                    "root": _ref(root) if not key.startswith("legacy:") else None,
                    "firstVisible": _ref(root),
                    "latestVisible": _ref(latest),
                    "opening": root.get("content") or "",
                    "visiblePoseCount": len(members),
                    "unread": unread,
                    "directUnread": 0,
                }
            )
            # `_page()`'s `_row_key()` fallback (`latestVisiblePose` or `pose` or the row
            # itself) needs one of those keys to resolve a boundary. Alias it to
            # `firstVisible`, NOT `latestVisible`: roots are sorted (and paged) by
            # creation time (see the sort below), and for a genuine multi-pose thread
            # `latestVisible` (the newest reply) can diverge sharply from that sort key,
            # desynchronizing `_page()`'s cursor-boundary search from the actual order.
            # (`_row_key`'s fallback chain only checks the key name, not its semantics.)
            results[-1]["latestVisiblePose"] = results[-1]["firstVisible"]
        results.sort(
            key=lambda item: (
                item["firstVisible"]["timestamp"],
                int(item["firstVisible"]["id"]),
            )
        )
        return _page(results, 20, request)


class PlayReadView(APIView):
    """POST authorized pose references to mark them read for this account."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        from world.scenes.read_state_services import (  # noqa: PLC0415
            MAX_POSES_PER_BATCH,
            mark_poses_read,
        )

        poses = request.data.get("poses", [])
        if not isinstance(poses, list) or len(poses) > MAX_POSES_PER_BATCH:
            return Response(
                {"detail": f"poses must be a list of at most {MAX_POSES_PER_BATCH} entries."},
                status=400,
            )
        pairs: list[tuple[int, str]] = []
        for entry in poses:
            try:
                pairs.append((int(entry["id"]), str(entry["timestamp"])))
            except (KeyError, TypeError, ValueError):
                return Response({"detail": "Each pose needs an id and a timestamp."}, status=400)
        marked = mark_poses_read(
            account=request.user,  # type: ignore[invalid-argument-type]
            poses=pairs,
        )
        return Response({"marked": marked})
