"""Authorized reader contracts for the narrative play workspace.

Also hosts ``PoseSubmissionDetailView`` (#3760) -- a writer-only
submission-status lookup by ``client_request_id``, the "did this land"
check the composer's "Check status" affordance calls after a reconnect or a
dropped connection leaves a send's outcome unknown.
"""

# ruff: noqa: EM101, TRY003
from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import date, datetime, timedelta
import hashlib
import json
import re
from typing import Any
import uuid

from django.core import signing
from django.db import transaction
from django.db.models import Q, QuerySet
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
from world.scenes.thread_services import thread_roots

SEARCH_MIN_LENGTH = 2
SEARCH_MAX_LENGTH = 200
DATE_ONLY_LENGTH = 10
TEMPORARY_AVAILABILITY = "temporary"
RETAINED_AVAILABILITY = "retained"


def _apply_history_bounds(
    queryset: QuerySet[Interaction], query_params: Mapping[str, str]
) -> QuerySet[Interaction]:
    """Apply inclusive lower/upper history bounds to a queryset."""
    since = query_params.get("from")
    if since:
        queryset = queryset.filter(timestamp__gte=since)
    until = query_params.get("to") or query_params.get("until")
    if not until:
        return queryset
    if len(until) != DATE_ONLY_LENGTH:
        return queryset.filter(timestamp__lte=until)
    try:
        exclusive_until = (date.fromisoformat(until) + timedelta(days=1)).isoformat()
    except ValueError:
        return queryset.filter(timestamp__lte=until)
    return queryset.filter(timestamp__lt=exclusive_until)


def _apply_conversation_bound(
    queryset: QuerySet[Interaction], conversation: str | None
) -> QuerySet[Interaction]:
    """Push simple conversation references into the authorized queryset."""
    if conversation and conversation.startswith("scene:"):
        return queryset.filter(scene_id=conversation.removeprefix("scene:"))
    if conversation and conversation.startswith("place:"):
        return queryset.filter(place_id=conversation.removeprefix("place:"))
    if conversation == GENERAL_CONVERSATION_KEY:
        return (
            queryset.filter(scene__isnull=True, place__isnull=True)
            .exclude(mode__in=set(OOC_MODES) | {TABLETALK_MODE})
            .exclude(receivers__isnull=False, mode=WHISPER_MODE)
        )
    if conversation and conversation.startswith("whisper:"):
        try:
            participant_ids = [
                int(value) for value in conversation.removeprefix("whisper:").split(",")
            ]
        except ValueError:
            return queryset.none()
        # A whisper reference is bound to its complete participant set. The
        # sender and every receiver are constrained in SQL before paging.
        return queryset.filter(
            mode=WHISPER_MODE,
            persona_id__in=participant_ids,
            receivers__persona_id__in=participant_ids,
        ).distinct()
    return queryset


class PlayCursorError(ValueError):
    """A cursor that cannot safely resume the requested reader query."""

    code = "invalid_cursor"

    def __init__(
        self, detail: str = "This history cursor is invalid. Reload and try again."
    ) -> None:
        super().__init__(detail)
        self.detail = detail


class PlayDateError(ValueError):
    """A malformed or timezone-less history date parameter."""

    code = "invalid_date"

    def __init__(self, field: str) -> None:
        super().__init__(f"{field} must be an ISO-8601 date or timestamp.")
        self.field = field
        self.detail = str(self)


_CURSOR_SALT = "narrative-play-cursor-v2"
_CURSOR_VERSION = 2


def _row_key(row: dict[str, Any]) -> tuple[str, int]:
    """Return the stable `(timestamp, id)` key for a serialized row."""
    pose = row.get("latestVisiblePose") or row.get("pose") or row
    return str(pose["timestamp"]), int(pose["id"])


def _datetime_param(value: str | None, field: str) -> datetime | None:
    """Parse one client date, rejecting malformed and timezone-less values."""
    if value is None or value == "":
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise PlayDateError(field)
    if timezone.is_naive(parsed):
        if len(value) == DATE_ONLY_LENGTH:
            parsed = timezone.make_aware(parsed)
        else:
            raise PlayDateError(field)
    return parsed


def _validate_history_dates(query_params: Mapping[str, str]) -> None:
    """Validate history bounds before django-filter can silently drop them."""
    for field in ("from", "to", "until"):
        _datetime_param(query_params.get(field), field)


def _same_instant(recorded: Any, requested: str) -> bool:
    """Compare two ISO timestamps by instant, not suffix spelling."""
    try:
        return datetime.fromisoformat(str(recorded)) == datetime.fromisoformat(requested)
    except ValueError:
        return str(recorded) == requested


def _cursor_context(_request: Request, query_params: Mapping[str, str]) -> str:
    """Hash all query filters that define a reader result set."""
    values = {
        key: str(query_params.get(key, ""))
        for key in sorted(query_params)
        if key not in {"before", "after", "snapshot"}
    }
    raw = json.dumps(values, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _encode_cursor(
    *,
    request: Request,
    query_params: Mapping[str, str],
    key: tuple[str, int],
    snapshot: tuple[str, int],
    direction: str,
) -> str:
    """Sign a cursor with viewer, filter, direction, and snapshot boundaries."""
    payload = {
        "v": _CURSOR_VERSION,
        "viewer": str(request.user.pk),
        "context": _cursor_context(request, query_params),
        "key": [key[0], key[1]],
        "snapshot": [snapshot[0], snapshot[1]],
        "direction": direction,
    }
    return signing.dumps(payload, salt=_CURSOR_SALT, compress=True)


def _decode_cursor(
    token: str, *, request: Request, query_params: Mapping[str, str]
) -> dict[str, Any]:
    """Verify and decode a bound cursor, raising a typed retryable error."""
    if not token:
        raise PlayCursorError
    try:
        payload = signing.loads(token, salt=_CURSOR_SALT, max_age=None)
    except (signing.BadSignature, ValueError, TypeError):
        # Accept pre-v2 cursors only as a one-way migration path. They remain
        # authorization checked by the queryset, but cannot carry a snapshot.
        try:
            padded = token + "=" * (-len(token) % 4)
            timestamp, row_id = json.loads(base64.urlsafe_b64decode(padded).decode())
            return {
                "key": [str(timestamp), int(row_id)],
                "snapshot": [str(timestamp), int(row_id)],
                "legacy": True,
            }
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            raise PlayCursorError from None
    if (
        payload.get("v") != _CURSOR_VERSION
        or str(payload.get("viewer")) != str(request.user.pk)
        or payload.get("context") != _cursor_context(request, query_params)
        or payload.get("direction") not in {"before", "after"}
    ):
        raise PlayCursorError(
            "This history cursor no longer matches the current view. Reload and try again."
        )
    try:
        key = [str(payload["key"][0]), int(payload["key"][1])]
        snapshot = [str(payload["snapshot"][0]), int(payload["snapshot"][1])]
    except (KeyError, IndexError, TypeError, ValueError):
        raise PlayCursorError from None
    return {"key": key, "snapshot": snapshot, "direction": payload["direction"]}


def _cursor(row: dict[str, Any]) -> str:
    """Encode the legacy `(timestamp, id)` boundary for old callers/tests."""
    value = json.dumps(list(_row_key(row)), separators=(",", ":"))
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _page(results: list[dict[str, Any]], limit: int, request: Request) -> Response:
    """Return a legacy in-memory page envelope.

    New interaction endpoints use `_paged_rows`; this remains for summary
    groups and compatibility with clients that supplied the original cursor.
    """
    before_token = request.query_params.get("before")
    after_token = request.query_params.get("after")
    start_index = max(0, len(results) - limit)
    end_index = len(results)
    if before_token or after_token:
        token = before_token or after_token
        if token is None:
            return Response(
                {"code": "invalid_cursor", "detail": "This history cursor is invalid."}, status=400
            )
        try:
            decoded = _decode_cursor(token, request=request, query_params=request.query_params)
            boundary = tuple(decoded["key"])
        except PlayCursorError:
            return Response(
                {
                    "code": "invalid_cursor",
                    "detail": "This history cursor is invalid. Reload and try again.",
                },
                status=400,
            )
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
    query_params = request.query_params if params is None else params
    _validate_history_dates(query_params)
    view = InteractionViewSet()
    view.request = request
    view.args = ()
    view.kwargs = {}
    view.format_kwarg = None
    queryset = view.get_queryset()
    query_params = request.query_params if params is None else params
    queryset = _apply_history_bounds(queryset, query_params)
    queryset = InteractionFilter(query_params, queryset=queryset).qs
    conversation = query_params.get("conversation")
    queryset = _apply_conversation_bound(queryset, conversation)
    # History is recent by default. `all=1` is the explicit older-history
    # override used by the navigator; an explicit `from` also opts in.
    if (
        not query_params.get("from")
        and not query_params.get("since")
        and str(query_params.get("all", "")) not in {"1", "true"}
    ):
        queryset = queryset.filter(timestamp__gte=timezone.now() - timedelta(days=90))
    thread = query_params.get("thread")
    if thread:
        try:
            queryset = queryset.filter(thread_id=int(thread))
        except (TypeError, ValueError):
            raise PlayDateError("thread") from None
    character = query_params.get("character") or query_params.get("relevant_character")
    if character:
        try:
            character_id = int(character)
        except (TypeError, ValueError):
            raise PlayDateError("character") from None
        queryset = queryset.filter(
            Q(persona_id=character_id)
            | Q(target_personas__id=character_id)
            | Q(receivers__persona_id=character_id)
        ).distinct()
    if str(query_params.get("relevant", "")).lower() in {"1", "true", "yes"}:
        relevant_ids = get_account_personas(request)
        queryset = queryset.filter(
            Q(persona_id__in=relevant_ids)
            | Q(target_personas__id__in=relevant_ids)
            | Q(receivers__persona_id__in=relevant_ids)
        ).distinct()
    search_text = query_params.get("q")
    if search_text:
        # Candidate narrowing is DB bounded; the final match still uses the
        # viewer-rendered serializer text below so masking/comprehension rules
        # cannot leak content.
        queryset = queryset.filter(content__icontains=search_text)
    return queryset.order_by("timestamp", "id"), view.get_serializer_context()


def _paged_rows(  # noqa: C901, PLR0912
    request: Request, *, limit: int, params: Mapping[str, str] | None = None
) -> tuple[list[dict[str, Any]], dict[str, str | None]]:
    """Fetch and enrich only one database-bounded keyset page.

    Visibility, filters, date bounds, snapshot, and cursor boundaries are all
    applied to the Interaction queryset before it is evaluated or serialized.
    The `(timestamp, id)` tie-breaker keeps equal timestamps and arrivals
    deterministic.
    """
    queryset, context = _queryset(request, params)
    token = request.query_params.get("before") or request.query_params.get("after")
    decoded = (
        _decode_cursor(token, request=request, query_params=request.query_params) if token else None
    )
    if decoded and not decoded.get("legacy"):
        expected_direction = "before" if request.query_params.get("before") else "after"
        if decoded.get("direction") != expected_direction:
            raise PlayCursorError(
                "This history cursor points in a different direction. Reload and try again."
            )
        raw_snapshot = decoded["snapshot"]
        snapshot = (str(raw_snapshot[0]), int(raw_snapshot[1]))
        snap_dt = _datetime_param(snapshot[0], "snapshot")
        if snap_dt is None:
            raise PlayCursorError
        queryset = queryset.filter(timestamp__lte=snap_dt)
    else:
        # `now` is a stable upper bound for this request and avoids a second
        # unbounded aggregate query. The id tie-breaker is deliberately maxed
        # so equal-timestamp rows remain eligible while the timestamp snapshot
        # excludes concurrent arrivals after this request began.
        snapshot = (timezone.now().isoformat(), 2**63 - 1)
        snap_dt = _datetime_param(snapshot[0], "snapshot")
        queryset = queryset.filter(timestamp__lte=snap_dt)
    if decoded:
        key = decoded["key"]
        boundary_dt = _datetime_param(key[0], "cursor")
        if boundary_dt is None:
            raise PlayCursorError
        boundary_id = int(key[1])
        if not queryset.filter(pk=boundary_id, timestamp=boundary_dt).exists():
            raise PlayCursorError("This history cursor is stale. Reload and try again.")
        after = bool(request.query_params.get("after"))
        if after:
            queryset = queryset.filter(
                Q(timestamp__gt=boundary_dt) | Q(timestamp=boundary_dt, id__gt=boundary_id)
            )
            queryset = queryset.order_by("timestamp", "id")
        else:
            queryset = queryset.filter(
                Q(timestamp__lt=boundary_dt) | Q(timestamp=boundary_dt, id__lt=boundary_id)
            )
            queryset = queryset.order_by("-timestamp", "-id")
    else:
        after = True
        queryset = queryset.order_by("timestamp", "id")
    rows = list(queryset[: limit + 1])
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    if not after:
        rows.reverse()
    serialized = list(InteractionListSerializer(rows, many=True, context=context).data)
    keys = [_row_key(row) for row in serialized]
    if not keys:
        return [], {"before": None, "after": None, "snapshot": _iso_snapshot(snapshot)}
    # The page probe (`limit + 1`) tells us whether a forward page exists.
    # A prior cursor implies an older page exists; on the initial page we expose
    # a backward control conservatively and stale resolution keeps it safe.
    has_after = has_more
    has_before = bool(decoded) or not request.query_params.get("before")
    before_cursor = (
        _encode_cursor(
            request=request,
            query_params=request.query_params,
            key=keys[0],
            snapshot=snapshot,
            direction="before",
        )
        if has_before
        else None
    )
    after_cursor = (
        _encode_cursor(
            request=request,
            query_params=request.query_params,
            key=keys[-1],
            snapshot=snapshot,
            direction="after",
        )
        if has_after
        else None
    )
    return serialized, {
        "before": before_cursor,
        "after": after_cursor,
        "snapshot": _iso_snapshot(snapshot),
    }


def _iso_snapshot(snapshot: tuple[str, int]) -> str:
    """Render a cursor snapshot for clients without exposing query state."""
    return str(snapshot[0])


def _summary_page(
    results: list[dict[str, Any]], *, limit: int, request: Request, page: dict[str, str | None]
) -> Response:
    """Page grouped summaries while retaining the signed query snapshot."""
    results.sort(key=_row_key)
    visible = results[:limit]
    snapshot = page.get("snapshot")
    snapshot_key = (str(snapshot), 2**63 - 1) if snapshot else _row_key(visible[-1])
    before = None
    after = None
    if request.query_params.get("after") or page.get("before"):
        before = (
            _encode_cursor(
                request=request,
                query_params=request.query_params,
                key=_row_key(visible[0]),
                snapshot=snapshot_key,
                direction="before",
            )
            if visible
            else None
        )
    if page.get("after") or len(results) > limit:
        after = (
            _encode_cursor(
                request=request,
                query_params=request.query_params,
                key=_row_key(visible[-1]),
                snapshot=snapshot_key,
                direction="after",
            )
            if visible
            else None
        )
    return Response({"results": visible, "before": before, "after": after, "snapshot": snapshot})


def _exchange_keys(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Map each thread on the page to the exchange it belongs to (#3787).

    An exchange is a whole nesting tree. Answering an unanswered reply moves that
    reply into a child thread, so one back-and-forth spans several threads; every
    thread in the tree shares one ``root``, which is the key they collapse onto.

    That collapse is also what satisfies the render rule for a single thread -
    "its own members plus the first member of each child thread". Grouping by root
    takes the union of every thread in the tree, so a row that moved into a child
    is still in the same group and nothing goes short. A caller that grouped by
    ``thread_id`` alone would lose one pose per answered child.

    ``root`` is derived, not stored - one query per nesting LEVEL for the whole
    page, never one per row (see ``thread_services.thread_roots``).
    """
    thread_ids = {str(row["thread_id"]) for row in rows if row.get("thread_id")}
    if not thread_ids:
        return {}
    return {str(pk): str(root) for pk, root in thread_roots(thread_ids).items()}


def _ref(row: dict[str, Any]) -> dict[str, str]:
    return {"id": str(row["id"]), "timestamp": row["timestamp"]}


def _read_pair(row: dict[str, Any]) -> tuple[int, datetime] | None:
    """Normalize a serialized row to the receipt's canonical pair."""
    timestamp = parse_datetime(str(row["timestamp"]))
    if timestamp is None:
        return None
    return int(row["id"]), timestamp


def _read_pairs_for_rows(rows: list[dict[str, Any]]) -> set[tuple[int, datetime]]:
    """Return exact read pairs for serialized rows, ignoring malformed rows."""
    return {pair for row in rows if (pair := _read_pair(row)) is not None}


def _directed_to_account(row: dict[str, Any], persona_ids: set[int]) -> bool:
    """Whether a row directly targets one of the account's personas."""
    targeted_ids = [
        *(row.get("receiver_persona_ids") or []),
        *(row.get("target_persona_ids") or []),
    ]
    targeted = {int(persona_id) for persona_id in targeted_ids}
    return bool(targeted & persona_ids)


def _unread_counts(
    rows: list[dict[str, Any]], read_pairs: set[tuple[int, datetime]], persona_ids: set[int]
) -> tuple[int, int]:
    """Count unread rows, excluding own poses and deriving direct attention."""
    unread = direct = 0
    for row in rows:
        pair = _read_pair(row)
        if pair is None or pair in read_pairs or int(row["persona"]["id"]) in persona_ids:
            continue
        unread += 1
        if _directed_to_account(row, persona_ids):
            direct += 1
    return unread, direct


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
) -> tuple[list[dict[str, Any]], list[Interaction]]:
    """Return serialized rows, and the same materialized interactions.

    Realizes the queryset exactly once (`list(queryset)`), then serializes that list -
    never the original queryset, which would otherwise evaluate the DB query a second
    time. Every caller here (PlayConversationsView, PlayPosesView, PlayContextView,
    PlaySearchView, PlayThreadsView, PlayReadView) goes through this one function.

    The reply parent chip needs nothing extra here: a row's thread IS its parent edge
    (#3787), and `InteractionViewSet.get_queryset` already joins `thread` in, so
    `get_reply_to` reads the anchor straight off each row.
    """
    queryset, context = _queryset(request, params)
    interactions = list(queryset)
    serialized = InteractionListSerializer(interactions, many=True, context=context).data
    return list(serialized), interactions


class PlayConversationsView(APIView):
    """GET authorized conversation summaries for the play navigator."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        try:
            # Grouping is done only over a bounded interaction window. The
            # authorized/keyset query is sliced before serializer enrichment.
            rows, page = _paged_rows(request, limit=300)
        except PlayDateError as exc:
            return Response(
                {"code": exc.code, "field": exc.field, "detail": exc.detail}, status=400
            )
        except PlayCursorError as exc:
            return Response({"code": exc.code, "detail": exc.detail, "retry": "reload"}, status=400)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            ref = _conversation(row)
            grouped.setdefault(f"{ref['kind']}:{ref['key']}", []).append(row)
        read_pairs: set[tuple[int, datetime]] = set()
        if request.user.is_authenticated and rows:
            from world.scenes.read_state_services import has_read_pairs  # noqa: PLC0415

            read_pairs = has_read_pairs(
                account=request.user,  # type: ignore[invalid-argument-type]
                poses=list(_read_pairs_for_rows(rows)),
            )
        persona_ids = set(get_account_personas(request))
        results = []
        for group in grouped.values():
            first, latest = group[0], group[-1]
            ref = _conversation(first)
            scene = first.get("scene")
            unread, direct_unread = _unread_counts(group, read_pairs, persona_ids)
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
                    # Direct unread spans every persona on this account;
                    # own-authored poses are excluded from both counters.
                    "directUnread": direct_unread,
                }
            )
        results.sort(key=lambda item: _row_key(item))
        return _summary_page(results, limit=30, request=request, page=page)


class PlayPosesView(APIView):
    """GET authorized poses using the existing enriched interaction DTO."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        try:
            rows, page = _paged_rows(request, limit=100)
        except PlayDateError as exc:
            return Response(
                {"code": exc.code, "field": exc.field, "detail": exc.detail}, status=400
            )
        except PlayCursorError as exc:
            return Response({"code": exc.code, "detail": exc.detail, "retry": "reload"}, status=400)
        return Response({"results": rows, **page})


class PlayContextView(APIView):
    """GET a small authorized context window around one retained pose."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        pose_id = request.query_params.get("id")  # noqa: USE_FILTERSET
        pose_timestamp = request.query_params.get("timestamp")  # noqa: USE_FILTERSET
        if not pose_id:
            return Response({"detail": "A pose reference is required."}, status=400)
        try:
            _datetime_param(pose_timestamp, "timestamp")
            queryset, context = _queryset(request)
            try:
                pose_pk = int(pose_id)
            except (TypeError, ValueError):
                return Response({"detail": "This pose is no longer available."}, status=404)
            target = queryset.filter(pk=pose_pk).first()
            if target is None or (
                pose_timestamp and not _same_instant(target.timestamp.isoformat(), pose_timestamp)
            ):
                return Response({"detail": "This pose is no longer available."}, status=404)
            # Resolve only a bounded authorized neighborhood. The target itself
            # is resolved before enrichment, so inaccessible ids cannot reveal
            # existence through a serializer or a broad materialized list.
            older_qs = queryset.filter(
                Q(timestamp__lt=target.timestamp) | Q(timestamp=target.timestamp, id__lt=target.pk)
            ).order_by("-timestamp", "-id")[:25]
            newer_qs = queryset.filter(
                Q(timestamp__gt=target.timestamp) | Q(timestamp=target.timestamp, id__gt=target.pk)
            ).order_by("timestamp", "id")[:25]
            older = list(reversed(list(older_qs)))
            newer = list(newer_qs)
            interactions = [*older, target, *newer]
            rows = list(InteractionListSerializer(interactions, many=True, context=context).data)
            latest = queryset.order_by("-timestamp", "-id").values("timestamp", "id").first()
            snapshot = (
                [latest["timestamp"].isoformat(), int(latest["id"])]
                if latest
                else [target.timestamp.isoformat(), target.pk]
            )
            has_older = queryset.filter(
                Q(timestamp__lt=target.timestamp) | Q(timestamp=target.timestamp, id__lt=target.pk)
            ).exists()
            has_newer = queryset.filter(
                Q(timestamp__gt=target.timestamp) | Q(timestamp=target.timestamp, id__gt=target.pk)
            ).exists()
            return Response(
                {
                    "results": rows,
                    "threadId": rows[len(older)].get("thread_id"),
                    # Context cursors retain the original compact shape for
                    # deep-link compatibility; each boundary is still resolved
                    # against the authorized queryset on the next request.
                    "before": _cursor(rows[0]) if has_older else None,
                    "after": _cursor(rows[-1]) if has_newer else None,
                    "snapshot": snapshot[0],
                }
            )
        except PlayDateError as exc:
            return Response(
                {"code": exc.code, "field": exc.field, "detail": exc.detail}, status=400
            )
        except PlayCursorError as exc:
            return Response({"code": exc.code, "detail": exc.detail, "retry": "reload"}, status=400)


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
        try:
            rows, page = _paged_rows(request, limit=30)
        except PlayDateError as exc:
            return Response(
                {"code": exc.code, "field": exc.field, "detail": exc.detail}, status=400
            )
        except PlayCursorError as exc:
            return Response({"code": exc.code, "detail": exc.detail, "retry": "reload"}, status=400)
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
        return Response({"results": results, **page})


class PlayThreadsView(APIView):
    """GET server-grouped, paginated thread summaries for one conversation."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        conversation = request.query_params.get("conversation")  # noqa: USE_FILTERSET
        if not conversation:
            return Response({"detail": "A conversation reference is required."}, status=400)
        legacy_mock = _rows.__module__ != __name__
        if legacy_mock:
            rows, _ = _rows(request)
            page = None
        else:
            try:
                rows, page = _paged_rows(request, limit=300)
            except PlayDateError as exc:
                return Response(
                    {"code": exc.code, "field": exc.field, "detail": exc.detail}, status=400
                )
            except PlayCursorError as exc:
                return Response(
                    {"code": exc.code, "detail": exc.detail, "retry": "reload"}, status=400
                )
        rows = [row for row in rows if _conversation(row)["key"] == conversation]
        read_pairs: set[tuple[int, datetime]] = set()
        if request.user.is_authenticated and rows:
            from world.scenes.read_state_services import has_read_pairs  # noqa: PLC0415

            read_pairs = has_read_pairs(
                account=request.user,  # type: ignore[invalid-argument-type]
                poses=list(_read_pairs_for_rows(rows)),
            )
        persona_ids = set(get_account_personas(request))
        # An exchange is the whole nesting tree, not one thread (#3787): answering an
        # unanswered reply moves it into a child thread, so one back-and-forth spans
        # several threads that share a root. Grouping by that root is also what keeps
        # a thread's display whole - see `_exchange_keys`.
        exchange_of = _exchange_keys(rows)

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            # An interaction carries a thread only when it is an explicit reply
            # (`interaction_services.create_interaction`), so ordinary narration,
            # the common case, belongs to no thread. This view is an index of
            # reply threads for one conversation, not a second pose feed: emitting
            # a single-pose group per unreplied pose made a 47-pose scene with 3
            # reply chains report 47 threads across 3 server-paged pages, which a
            # client cannot filter because the paging is server side (#3772).
            # `ThreadedNarrativeReader` draws the same line client side for its own
            # collapse seeding, where it excludes `legacy:`-keyed groups.
            key = row.get("thread_id")
            if not key:
                continue
            exchange = exchange_of.get(str(key))
            if exchange is None:
                continue
            grouped.setdefault(exchange, []).append(row)
        results = []
        for key, members in grouped.items():
            # The answered pose is a real MEMBER of its thread now (#3787), so it is
            # already in `members` and opens the exchange on its own - no row has to
            # be fetched from outside the group and spliced in, which is what used to
            # risk counting one pose in two groups. `rows` is ordered by (timestamp,
            # id), so `members[0]` is the earliest pose of the exchange the viewer
            # can see, which is exactly what `root`/`firstVisible` mean.
            root, latest = members[0], members[-1]
            unread, direct_unread = _unread_counts(members, read_pairs, persona_ids)
            results.append(
                {
                    "id": key,
                    "conversation": _conversation(root),
                    "root": _ref(root),
                    "firstVisible": _ref(root),
                    "latestVisible": _ref(latest),
                    "opening": root.get("content") or "",
                    "visiblePoseCount": len(members),
                    "unread": unread,
                    "directUnread": direct_unread,
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
        return (
            _page(results, 20, request)
            if page is None
            else _summary_page(results, limit=20, request=request, page=page)
        )


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
            ReadBatchAuthorizationError,
            authorize_read_pairs,
            mark_poses_read,
        )

        poses = request.data.get("poses", [])
        if not isinstance(poses, list) or len(poses) > MAX_POSES_PER_BATCH:
            return Response(
                {"detail": f"poses must be a list of at most {MAX_POSES_PER_BATCH} entries."},
                status=400,
            )
        pairs: list[tuple[int, str]] = []
        try:
            pairs = [(int(entry["id"]), str(entry["timestamp"])) for entry in poses]
        except (KeyError, TypeError, ValueError):
            return Response({"detail": "Unable to authorize read batch."}, status=400)

        # Authorize the complete batch against the same visibility queryset used
        # by every play GET before writing anything. This prevents forged,
        # stale, hidden, deleted, and timestamp-mismatched pairs from producing
        # partial receipts.
        try:
            with transaction.atomic():
                queryset, _ = _queryset(request)
                authorized = authorize_read_pairs(queryset=queryset, poses=pairs)
                marked = mark_poses_read(
                    account=request.user,  # type: ignore[invalid-argument-type]
                    poses=authorized,
                )
        except ReadBatchAuthorizationError:
            return Response({"detail": "Unable to authorize read batch."}, status=400)
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
        queryset, _ = _queryset(request, params={"conversation": conversation, "to": before})
        # This operation deliberately reads only the canonical key columns;
        # no serializer enrichment or full in-memory row list is needed.
        pairs = [
            (int(row_id), timestamp.isoformat())
            for row_id, timestamp in queryset.values_list("id", "timestamp")
        ]
        marked = mark_conversation_read(
            account=request.user,  # type: ignore[invalid-argument-type]
            poses=pairs,
        )
        return Response({"marked": marked})
