"""Authorized reader contracts for the narrative play workspace.

Also hosts ``PoseSubmissionDetailView`` (#3760) -- a writer-only
submission-status lookup by ``client_request_id``, the "did this land"
check the composer's "Check status" affordance calls after a reconnect or a
dropped connection leaves a send's outcome unknown.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import date, datetime, timedelta
import json
import re
from typing import Any
import uuid

from django.db.models import QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.scenes.constants import (
    GENERAL_CONVERSATION_KEY,
    KIND_CHANNEL,
    KIND_PLACE,
    KIND_ROOM,
    KIND_SCENE_OOC,
    KIND_WHISPER,
    OOC_MODES,
    TABLETALK_MODE,
    WHISPER_MODE,
)
from world.scenes.interaction_filters import InteractionFilter
from world.scenes.interaction_permissions import get_account_personas
from world.scenes.interaction_serializers import InteractionListSerializer
from world.scenes.interaction_views import InteractionViewSet
from world.scenes.models import Interaction, PoseSubmission

SEARCH_MIN_LENGTH = 2
SEARCH_MAX_LENGTH = 200
DATE_ONLY_LENGTH = 10
TEMPORARY_AVAILABILITY = "temporary"
RETAINED_AVAILABILITY = "retained"


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
    page = results[start_index : min(start_index + limit, end_index)]
    # Backward-cursor asymmetry (#3759 review finding, minor fold-in): paging
    # backward (`before`) always computes `start_index + len(page) == end_index`
    # by construction, so `after` below is always `None` on that response -- a
    # client that pages backward has no cursor to then page forward again from.
    # Not reachable today (no frontend caller ever sends a bare `before` without
    # also re-deriving `after` some other way), so no behavior change here --
    # just flagging the gap for whoever extends paging next.
    return Response(
        {
            "results": page,
            "before": _cursor(page[0]) if start_index > 0 and page else None,
            "after": _cursor(page[-1]) if start_index + len(page) < end_index and page else None,
            "snapshot": timezone.now().isoformat(),
        }
    )


def _queryset(
    request: Request, params: Mapping[str, str] | None = None
) -> tuple[QuerySet[Interaction], dict[str, Any]]:
    """Build the canonical visible interaction queryset and serializer context.

    The play endpoints intentionally reuse ``InteractionViewSet``. This keeps
    masking, language comprehension, block/mute rules, and private-party
    visibility identical to the existing scene feed.

    `params` overrides `request.query_params` as the source of `from`/`to`/
    `until`/`conversation` filter values — used by `PlayReadView`'s bulk
    mark-conversation-read path (#3759), whose `conversation`/`before` are
    POST body fields rather than query-string params, so it can still push
    its `timestamp <= before` bound into the SAME authorized DB query every
    GET-based play view uses, instead of filtering in Python after the fact.
    """
    view = InteractionViewSet()
    view.request = request
    view.args = ()
    view.kwargs = {}
    view.format_kwarg = None
    queryset = view.get_queryset()
    query_params = request.query_params if params is None else params
    # ``from`` is the UI spelling for an explicit older-history lower bound.
    since = query_params.get("from")
    until = query_params.get("to") or query_params.get("until")
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
    queryset = InteractionFilter(query_params, queryset=queryset).qs
    # scene:/room/place: refs push down into the DB filter (`place` is a
    # plain FK column on the row, same as `scene`). `whisper:<comma-joined
    # ids>` does NOT -- pushing it down needs a participant-set EXACT-match
    # (not merely "any receiver present", which `filter_kind`'s
    # `Exists`/`OuterRef` pattern gives you), a bigger lift than a filter
    # branch. A whisper-scoped `conversation` therefore still falls back to
    # scanning all visible history in Python at each of this function's
    # callers -- including `PlayReadView._mark_conversation_read`'s
    # `pairs = [... if _conversation(row)["key"] == conversation]` filter,
    # not just `PlaySearchView` (see its own `has_bound` comment for the same
    # gap). This whisper gap IS reachable in production, not just a
    # theoretical one: `HistoryNavigator.tsx`'s search form offers a
    # "Whispers" type, `onOpenReference` carries the backend's own
    # `whisper:<ids>` ref straight through as `GameWindow.tsx`'s
    # `conversationRef`, and "Mark conversation read" has no `readOnly` guard
    # -- so clicking it while reading a whisper reference posts exactly this
    # unbounded-scan shape. The result is still correct (bounded only by the
    # `to=before` snapshot, which happens to be the conversation's own latest
    # timestamp) -- this is a scan-size/performance gap, not a data-integrity
    # one -- but it is NOT "unreachable," and no future edit should assume it is.
    conversation = query_params.get("conversation")
    if conversation and conversation.startswith("scene:"):
        queryset = queryset.filter(scene_id=conversation.removeprefix("scene:"))
    elif conversation and conversation.startswith("place:"):
        queryset = queryset.filter(place_id=conversation.removeprefix("place:"))
    elif conversation == GENERAL_CONVERSATION_KEY:
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
            "kind": KIND_WHISPER,
            "key": "whisper:" + ",".join(str(i) for i in sorted(set(participants))),
        }
    place = row.get("place")
    if place is not None:
        return {"kind": KIND_PLACE, "key": f"place:{place}"}
    if mode in OOC_MODES:
        return {"kind": KIND_SCENE_OOC, "key": mode}
    if mode == TABLETALK_MODE:
        return {"kind": KIND_CHANNEL, "key": "tt"}
    scene = row.get("scene")
    if scene is not None:
        return {"kind": KIND_ROOM, "key": f"scene:{scene}"}
    return {"kind": KIND_ROOM, "key": GENERAL_CONVERSATION_KEY}


_SCENE_REF_RE = re.compile(r"^scene:\d+$")
_PLACE_REF_RE = re.compile(r"^place:\d+$")
_WHISPER_REF_RE = re.compile(r"^whisper:\d+(?:,\d+)*$")


def _is_recognized_conversation_ref(ref: str) -> bool:
    """Whether `ref` matches one of `_conversation()`'s own possible output shapes.

    Kept in the same lockstep-with-`_conversation()` discipline `constants.py`'s
    module comment already documents for `filter_kind`/`_conversation()` -- this
    is the third function that must recognize exactly the ref shapes
    `_conversation()` can produce, so it walks the same branches: the general/
    no-scene room (`GENERAL_CONVERSATION_KEY`), a scene-attached conversation
    (`scene:<id>`), a place (`place:<id>`), a whisper (`whisper:<comma-joined
    ids>`), the tabletalk channel (`TABLETALK_MODE`), and the forward-compatible
    OOC modes (`OOC_MODES`) -- see the constants module for why the latter two
    are dead branches today.

    `PlayReadView._mark_conversation_read` uses this to reject a caller-supplied
    ref that doesn't match ANY recognized shape (#3759 review finding C1) --
    without it, an unrecognized ref like a bare pose id silently matched no
    `_queryset` branch (so no scene filter applied at all) and then matched no
    row's own `_conversation()` key either, so the whole request serialized the
    account's entire visible history, wrote nothing, and reported success.
    """
    if ref == GENERAL_CONVERSATION_KEY:
        return True
    if ref == TABLETALK_MODE:
        return True
    if ref in OOC_MODES:
        return True
    return bool(_SCENE_REF_RE.match(ref) or _PLACE_REF_RE.match(ref) or _WHISPER_REF_RE.match(ref))


def _rows(
    request: Request, params: Mapping[str, str] | None = None
) -> tuple[list[dict[str, Any]], QuerySet[Interaction]]:
    queryset, context = _queryset(request, params)
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
        read_ids: set[int] = set()
        if request.user.is_authenticated and rows:
            from world.scenes.read_state_services import has_read  # noqa: PLC0415

            read_ids = has_read(
                account=request.user,  # type: ignore[invalid-argument-type]
                interaction_ids=[row["id"] for row in rows],
            )
        results = []
        for group in grouped.values():
            first, latest = group[0], group[-1]
            ref = _conversation(first)
            scene = first.get("scene")
            unread = sum(1 for row in group if int(row["id"]) not in read_ids)
            results.append(
                {
                    "ref": ref,
                    "title": f"Scene {scene}" if scene is not None else "General conversation",
                    "availability": RETAINED_AVAILABILITY,
                    "canRead": True,
                    "canSend": False,
                    "sceneId": str(scene) if scene is not None else None,
                    "latestVisiblePose": _ref(latest),
                    "unread": unread,
                    # `directUnread` -- specifically-addressed-to-me unread --
                    # requires knowing the current persona's own targeting, a
                    # gap `PlayThreadsView` also leaves at 0 today (#3759 spec's
                    # own staging note); consistent, not a new gap to fix here.
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
        # Finding 6.1 (#3760 final review): only `interaction_id` (a plain FK
        # column already on this row) is read below -- `.interaction` (the
        # related object) is never touched, so the `select_related` inherited
        # from an earlier ViewSet-shaped draft of this endpoint was a wasted
        # join. Dropped.
        submission = PoseSubmission.objects.filter(
            persona_id__in=persona_ids,
            client_request_id=client_request_id,
        ).first()
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
        # Accepts `conversation=whisper:<ids>` as a valid bound, but
        # `_queryset` below still doesn't push a whisper-scoped conversation
        # down into the DB filter (place: now does -- see `_queryset`'s own
        # comment for why whisper: is the harder case) -- a whisper-scoped
        # search silently falls back to scanning all of this account's
        # visible history in Python instead. NOT reachable from the current
        # UI on THIS path specifically (`HistoryNavigator`'s search call never
        # sends a bare `conversation` param at all, only `from`/`to`/`kind`)
        # -- unlike `_mark_conversation_read`'s own whisper gap, which IS
        # reachable (see `_queryset`'s comment) -- so no behavior change here,
        # just flagged so the next person extending search doesn't assume
        # `conversation` is always pushed down to the query.
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
        if not conversation:
            return Response({"detail": "A conversation reference is required."}, status=400)
        rows, _ = _rows(request)
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
    """POST authorized pose references to mark them read for this account.

    Two request-body shapes:

    - ``{"poses": [{"id": ..., "timestamp": ...}, ...]}`` — the original
      explicit-list path, capped at ``MAX_POSES_PER_BATCH``.
    - ``{"conversation": "<ref>", "before": "<ISO-8601 timestamp>"}`` — the
      mark-all-before-snapshot bulk dismissal (#3759 spec section 7: "Separate
      explicit mark-all-before-snapshot operation for deliberate dismissal.").
      Marks every interaction this account can see in that conversation with
      ``timestamp <= before`` as read, without the client enumerating poses.

    Supplying both ``conversation`` and ``poses`` in the same request is
    rejected with 400 rather than silently favoring one shape.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        conversation = request.data.get("conversation")
        # Both shapes present is an ambiguous request -- silently favoring one
        # (the bulk path, previously) would drop the caller's `poses` list with
        # no signal that it was ignored. Reject instead of guessing.
        if conversation and request.data.get("poses") is not None:
            return Response(
                {"detail": "Supply either 'poses' or 'conversation', not both."},
                status=400,
            )
        if conversation:
            return self._mark_conversation_read(request, conversation)
        return self._mark_poses_read(request)

    def _mark_poses_read(self, request: Request) -> Response:
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

    def _mark_conversation_read(self, request: Request, conversation: Any) -> Response:
        from world.scenes.read_state_services import mark_conversation_read  # noqa: PLC0415

        if not isinstance(conversation, str):
            return Response({"detail": "conversation must be a string reference."}, status=400)
        if not _is_recognized_conversation_ref(conversation):
            return Response(
                {"detail": "conversation is not a recognized conversation reference."},
                status=400,
            )
        before = request.data.get("before")
        if not isinstance(before, str) or parse_datetime(before) is None:
            return Response(
                {"detail": "before must be an ISO-8601 timestamp."},
                status=400,
            )
        # Push the `timestamp <= before` bound into the SAME authorized DB
        # query every GET-based play view builds (`_queryset`'s `to` alias),
        # rather than fetching this account's entire visible history and
        # filtering in Python — see `_queryset`'s `params` docstring.
        rows, _ = _rows(request, params={"conversation": conversation, "to": before})
        pairs = [
            (int(row["id"]), str(row["timestamp"]))
            for row in rows
            if _conversation(row)["key"] == conversation
        ]
        marked = mark_conversation_read(
            account=request.user,  # type: ignore[invalid-argument-type]
            poses=pairs,
        )
        return Response({"marked": marked})
