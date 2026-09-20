"""API views for the journal system."""

from __future__ import annotations

import dataclasses

from django.db.models import Prefetch, QuerySet
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.fields import DateTimeField
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from actions.registry import get_action
from web.api.mixins import CharacterContextMixin
from world.character_sheets.models import CharacterSheet
from world.journals.filters import JournalEntryFilter, JournalFilterBackend
from world.journals.models import JournalEntry, JournalTag
from world.journals.serializers import (
    JournalEntryCreateSerializer,
    JournalEntryDetailSerializer,
    JournalEntryEditSerializer,
    JournalEntryListSerializer,
    JournalResponseCreateSerializer,
    JournalSettingsSerializer,
)
from world.journals.services import (
    annotate_can_retort,
    base_entries_queryset,
    entry_visible_via_bequest,
    exclude_blocked_and_muted_authors,
    journal_settings,
    mark_journals_visited,
    visible_entries_q,
)

_NO_CHARACTER_DETAIL = "No character found."
_NOT_FOUND_DETAIL = "Not found."
# Serializer/validated_data field names, extracted to satisfy the string-literal lint
# (tools/lint_string_literal.py) at their "<name> in ..." membership checks below.
_ABOUT_FIELD = "about"
_DISPOSITION_FIELD = "disposition"
_RETORT_CONSENT_FIELD = "retort_consent"

# The visit mark goes out through DRF's own DateTimeField so ``visited_at`` is spelled like
# every other timestamp in the payload (a trailing "Z" rather than "+00:00") -- the client
# hands it straight back as ``?since=``, and a literal "+" in a query string decodes as a
# space.
_VISIT_MARK_FIELD = DateTimeField()


def _truthy_param(value: str | None) -> bool:
    """Parse a raw query-string flag the way the FilterSet's booleans do (#3941).

    ``mark_visit`` is a one-shot side effect (see ``list()``), not a FilterSet field, so
    it never goes through ``django_filters.rest_framework.filters.BooleanFilter``'s own
    widget parsing. Matching that parsing here (rather than plain Python truthiness on
    the string) matters because ``bool("0")`` is ``True`` — a bare truthiness check
    would treat ``?mark_visit=0`` as a request to mark the visit.
    """
    return value is not None and value.lower() in ("1", "true", "yes")


class JournalEntryPagination(PageNumberPagination):
    """Pagination for journal entries."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class JournalEntryViewSet(CharacterContextMixin, viewsets.GenericViewSet):
    """
    ViewSet for journal entries.

    Endpoints:
    - GET  /entries/        — list public entries (supports ?author, ?tag, ?deceased filters)
    - GET  /entries/mine/   — list own entries including private
    - GET  /entries/<id>/   — retrieve single entry
    - POST /entries/        — create a new entry
    - PATCH /entries/<id>/  — edit an entry (owner only)
    - POST /entries/<id>/respond/ — create praise/retort response
    - GET/PATCH /entries/disposition/ — read/set the caller's sheet-level default
      posthumous journal disposition (#3287)
    """

    permission_classes = [IsAuthenticated]
    pagination_class = JournalEntryPagination
    filter_backends = [JournalFilterBackend]
    filterset_class = JournalEntryFilter

    @staticmethod
    def _get_base_queryset() -> QuerySet[JournalEntry]:
        """Base queryset with annotations and prefetches (shared with the FilterSet, #3287)."""
        return base_entries_queryset()

    @staticmethod
    def _get_entry_for_response(pk: int) -> JournalEntry:
        """Re-fetch an entry with relations needed for detail serialization."""
        return (
            JournalEntry.objects.select_related("author__character", "about__character")
            .prefetch_related(
                Prefetch("tags", queryset=JournalTag.objects.all(), to_attr="cached_tags"),
                Prefetch(
                    "responses",
                    queryset=JournalEntry.objects.select_related("author__character"),
                    to_attr="cached_responses",
                ),
            )
            .get(pk=pk)
        )

    def get_character_sheet(self, request: Request) -> CharacterSheet | None:
        """Get the CharacterSheet for the requesting user's character.

        Public (not ``_``-prefixed, #3287) so ``JournalEntryFilter.filter_deceased`` can
        call it via ``self.view`` — the same viewer-resolution path (and the same
        ``_get_character`` mock point) every other method on this ViewSet uses.
        """
        character = self._get_character(request)
        if not character:
            return None
        try:
            return character.sheet_data
        except CharacterSheet.DoesNotExist:
            return None

    def get_queryset(self) -> QuerySet[JournalEntry]:
        """The visibility queryset ``filter_queryset()`` (writer/about/kind/... ) builds on.

        The one visibility rule (#3941 Decision 1, ``services.visible_entries_q``): public,
        revealed by an estate settlement, the viewer's own, or (staff) everything. Blocked/
        muted authors excluded (#2996 Decision 2) on top of that. ``?deceased=``
        (``JournalEntryFilter.filter_deceased``) replaces this queryset outright rather than
        narrowing it — the bequest corpus is a different shape (the deceased's non-sealed
        private+public entries), so this restriction is moot for that branch but harmless to
        compute either way (querysets are lazy).

        Carries the ``viewer_can_retort`` annotation (``services.annotate_can_retort``) the
        row serializer reads, so the Retort/Condemn predicate costs one EXISTS for the page
        rather than one per row.
        """
        sheet = self.get_character_sheet(self.request)
        queryset = self._get_base_queryset().filter(
            visible_entries_q(viewer_sheet=sheet, is_staff=self.request.user.is_staff)
        )
        queryset = exclude_blocked_and_muted_authors(queryset, viewer_account=self.request.user)
        return annotate_can_retort(queryset, sheet)

    def list(self, request: Request) -> Response:
        """
        List visible journal entries, or (with ``?deceased=``) a bequeathed corpus.

        Supports query params (all handled by ``JournalEntryFilter``):
        - ?author=<character_id> / ?writer=<name substring> — filter by author
        - ?tag=<tag_name> — filter by tag name
        - ?about=<character_sheet_id> — entries about that character (#3941)
        - ?kind=<JournalKind|introductions> — the CG Introductions alias (#3941)
        - ?post_mortem=1 — only entries revealed by an estate settlement (#3941)
        - ?since=<iso timestamp> — only entries created after that moment (#3941). The
          client passes back the ``visited_at`` this endpoint returned, which is the
          viewer's visit mark AS IT WAS before the request that opened the stream
          advanced it.
        - ?black_only=1 — staff-only: just the private entries (#3941)
        - ?mark_visit=1 — after computing ``since_visit_count`` and ``visited_at``, stamp
          the viewer's visit
        - ?deceased=<character_sheet_id> — browse a deceased sheet's non-sealed private
          entries, ONLY when the caller holds a ``JournalBequestGrant`` for that sheet
          (#3287 Decision 3, gated in ``JournalEntryFilter.filter_deceased`` per
          ``tools/lint_use_filterset.py``). Empty when no grant exists — never a permission
          error, so a probing id can't confirm whether a grant exists for someone else.
          This response's shape is unchanged from pre-#3941: no ``since_visit_count`` and
          no ``visited_at`` key, and ``?mark_visit=`` is ignored — the since-visit
          machinery only applies to the viewer's own stream, never the bequest corpus.

        See ``get_queryset()`` for the visibility contract (#3941 Decision 1, block/mute).
        """
        sheet = self.get_character_sheet(request)
        # A one-shot side-effect trigger (stamps the visit mark below), not a queryset
        # filter, so it has no FilterSet field to live on.
        mark_visit = request.query_params.get("mark_visit")  # noqa: USE_FILTERSET
        # ``?deceased=`` swaps in an entirely different corpus (the bequest read,
        # ``JournalEntryFilter.filter_deceased``) whose response keeps its pre-#3941
        # shape exactly — no ``since_visit_count`` key, no mark advance. Detecting the
        # raw param here (rather than teaching the since-visit concept to
        # filter_deceased) keeps that branch's contract unchanged.
        is_bequest_listing = request.query_params.get("deceased") is not None  # noqa: USE_FILTERSET

        queryset = self.filter_queryset(self.get_queryset())

        since_visit_count = None
        visited_at = None
        if not is_bequest_listing:
            # Both of these describe the reader's PREVIOUS visit, so both are read from the
            # mark as it was before this request advances it — never the other way around,
            # or a mark_visit=1 request would count against its own freshly-stamped mark
            # and always report zero. ``visited_at`` goes out so the client can ask for
            # that cut later (``?since=``): once the mark has moved to now, the server can
            # no longer name the moment the reader means by "since my last visit".
            previous_visit = sheet.journals_visited_at if sheet is not None else None
            count_qs = self.get_queryset()
            if previous_visit is not None:
                count_qs = count_qs.filter(created_at__gt=previous_visit)
            since_visit_count = count_qs.count()
            if previous_visit is not None:
                visited_at = _VISIT_MARK_FIELD.to_representation(previous_visit)

            if _truthy_param(mark_visit) and sheet is not None:
                mark_journals_visited(sheet=sheet, at=timezone.now())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = JournalEntryListSerializer(
                page, many=True, context={"viewer_sheet": sheet}
            )
            response = self.get_paginated_response(serializer.data)
            if not is_bequest_listing:
                response.data["since_visit_count"] = since_visit_count
                response.data["visited_at"] = visited_at
            return response

        return Response(
            JournalEntryListSerializer(queryset, many=True, context={"viewer_sheet": sheet}).data
        )

    @action(detail=False, methods=["get"])
    def mine(self, request: Request) -> Response:
        """List the requesting character's own entries (including private)."""
        sheet = self.get_character_sheet(request)
        if not sheet:
            return Response(
                {"detail": _NO_CHARACTER_DETAIL},
                status=status.HTTP_404_NOT_FOUND,
            )

        queryset = annotate_can_retort(self._get_base_queryset().filter(author=sheet), sheet)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = JournalEntryListSerializer(
                page, many=True, context={"viewer_sheet": sheet}
            )
            return self.get_paginated_response(serializer.data)

        return Response(
            JournalEntryListSerializer(queryset, many=True, context={"viewer_sheet": sheet}).data
        )

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """
        Retrieve a single journal entry.

        Visible when: public, revealed by an estate settlement, staff, authored by the
        caller, or (#3287 Decision 3) the caller holds a bequest grant over the author's
        writings and this entry's effective disposition isn't SEAL (#3941 Decision 1).
        """
        try:
            entry = (
                JournalEntry.objects.select_related("author__character", "about__character")
                .prefetch_related(
                    Prefetch("tags", queryset=JournalTag.objects.all(), to_attr="cached_tags"),
                    Prefetch(
                        "responses",
                        queryset=JournalEntry.objects.select_related("author__character"),
                        to_attr="cached_responses",
                    ),
                )
                .get(pk=pk)
            )
        except JournalEntry.DoesNotExist:
            return Response(
                {"detail": _NOT_FOUND_DETAIL},
                status=status.HTTP_404_NOT_FOUND,
            )

        sheet = self.get_character_sheet(request)
        is_own = sheet is not None and entry.author_id == sheet.pk
        visible = (
            entry.is_public
            or entry.revealed_at is not None
            or request.user.is_staff
            or is_own
            or entry_visible_via_bequest(entry, sheet)
        )
        if not visible:
            return Response(
                {"detail": _NOT_FOUND_DETAIL},
                status=status.HTTP_404_NOT_FOUND,
            )

        # #2996 Decision 2 — mute: a response persists normally (write-then-filter, never
        # skip-the-write) but is excluded from the entry AUTHOR's own view of responses to
        # THEIR entry when the author has muted the responder's account. Only applies when the
        # requester IS the entry's author; any other viewer sees the full response list.
        if is_own and entry.cached_responses:
            from world.journals.services import player_for_sheet  # noqa: PLC0415
            from world.scenes.mute_services import account_muted  # noqa: PLC0415

            author_player = player_for_sheet(sheet)
            if author_player is not None:
                entry.cached_responses = [
                    response
                    for response in entry.cached_responses
                    if not (
                        (responder_player := player_for_sheet(response.author)) is not None
                        and account_muted(
                            viewer_player=author_player, target_player=responder_player
                        )
                    )
                ]

        serializer = JournalEntryDetailSerializer(entry, context={"viewer_sheet": sheet})
        return Response(serializer.data)

    def create(self, request: Request) -> Response:
        """Create a new journal entry."""
        character = self._get_character(request)
        if not character:
            return Response(
                {"detail": _NO_CHARACTER_DETAIL},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = JournalEntryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = get_action("create_journal_entry").run(
            actor=character,
            title=serializer.validated_data["title"],
            body=serializer.validated_data["body"],
            is_public=serializer.validated_data["is_public"],
            tags=serializer.validated_data.get("tags"),
            posthumous_override=serializer.validated_data.get("posthumous_override"),
            about_id=serializer.validated_data.get("about"),
        )
        if not result.success:
            return Response(
                {"detail": result.message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        entry = self._get_entry_for_response(result.data["entry_id"])
        sheet = self.get_character_sheet(request)
        return Response(
            JournalEntryDetailSerializer(entry, context={"viewer_sheet": sheet}).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        """Edit an existing journal entry (owner only)."""
        character = self._get_character(request)
        if not character:
            return Response(
                {"detail": _NO_CHARACTER_DETAIL},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            sheet = character.sheet_data
        except CharacterSheet.DoesNotExist:
            return Response(
                {"detail": _NO_CHARACTER_DETAIL},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            entry = JournalEntry.objects.get(pk=pk, author_id=sheet.pk)
        except JournalEntry.DoesNotExist:
            return Response(
                {"detail": _NOT_FOUND_DETAIL},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = JournalEntryEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # "about" is optional AND nullable (null clears it), so its presence/absence in
        # validated_data — not its value — decides whether the action touches it at all.
        about_kwargs: dict[str, int | bool] = {}
        if _ABOUT_FIELD in serializer.validated_data:
            about_value = serializer.validated_data[_ABOUT_FIELD]
            if about_value is None:
                about_kwargs["clear_about"] = True
            else:
                about_kwargs["about_id"] = about_value

        result = get_action("edit_journal_entry").run(
            actor=character,
            entry=entry,
            title=serializer.validated_data.get("title"),
            body=serializer.validated_data.get("body"),
            posthumous_override=serializer.validated_data.get("posthumous_override"),
            **about_kwargs,
        )
        if not result.success:
            return Response(
                {"detail": result.message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = self._get_entry_for_response(result.data["entry_id"])
        return Response(JournalEntryDetailSerializer(updated, context={"viewer_sheet": sheet}).data)

    @action(detail=True, methods=["post"])
    def respond(self, request: Request, pk: str | None = None) -> Response:
        """Create a praise or retort response to a journal entry."""
        character = self._get_character(request)
        if not character:
            return Response(
                {"detail": _NO_CHARACTER_DETAIL},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            sheet = character.sheet_data
        except CharacterSheet.DoesNotExist:
            return Response(
                {"detail": _NO_CHARACTER_DETAIL},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            parent = JournalEntry.objects.select_related("author").get(pk=pk)
        except JournalEntry.DoesNotExist:
            return Response(
                {"detail": _NOT_FOUND_DETAIL},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = JournalResponseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = get_action("respond_to_journal").run(
            actor=character,
            parent=parent,
            response_type=serializer.validated_data["response_type"],
            title=serializer.validated_data["title"],
            body=serializer.validated_data["body"],
        )
        if not result.success:
            return Response(
                {"detail": result.message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_entry = self._get_entry_for_response(result.data["entry_id"])
        return Response(
            JournalEntryDetailSerializer(response_entry, context={"viewer_sheet": sheet}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get", "patch"])
    def disposition(self, request: Request) -> Response:
        """Read or set the owner's journal settings (#3287, #3941).

        GET returns ``posthumous_journal_disposition``, ``retort_consent``,
        ``posts_this_week``, and ``rewarded_posts_per_week``. PATCH accepts
        ``disposition`` and/or ``retort_consent`` (at least one required) and applies
        each through its own action — ``set_journal_disposition`` (#3287) and
        ``set_retort_consent`` (ADR-0307) — the same seams telnet's ``journal
        disposition``/``journal consent`` commands use.
        """
        sheet = self.get_character_sheet(request)
        if not sheet:
            return Response(
                {"detail": _NO_CHARACTER_DETAIL},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == "GET":
            return Response(dataclasses.asdict(journal_settings(sheet=sheet)))

        serializer = JournalSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        character = self._get_character(request)
        if _DISPOSITION_FIELD in serializer.validated_data:
            result = get_action("set_journal_disposition").run(
                actor=character,
                disposition=serializer.validated_data[_DISPOSITION_FIELD],
            )
            if not result.success:
                return Response(
                    {"detail": result.message},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if _RETORT_CONSENT_FIELD in serializer.validated_data:
            result = get_action("set_retort_consent").run(
                actor=character,
                consent=serializer.validated_data[_RETORT_CONSENT_FIELD],
            )
            if not result.success:
                return Response(
                    {"detail": result.message},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(dataclasses.asdict(journal_settings(sheet=sheet)))
