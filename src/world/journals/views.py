"""API views for the journal system."""

from __future__ import annotations

from django.db.models import Prefetch, Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from actions.registry import get_action
from web.api.mixins import CharacterContextMixin
from world.character_sheets.models import CharacterSheet
from world.journals.filters import JournalEntryFilter
from world.journals.models import JournalEntry, JournalTag
from world.journals.serializers import (
    JournalDispositionSerializer,
    JournalEntryCreateSerializer,
    JournalEntryDetailSerializer,
    JournalEntryEditSerializer,
    JournalEntryListSerializer,
    JournalResponseCreateSerializer,
)
from world.journals.services import (
    base_entries_queryset,
    entry_visible_via_bequest,
    exclude_blocked_and_muted_authors,
)


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
    filter_backends = [DjangoFilterBackend]
    filterset_class = JournalEntryFilter

    @staticmethod
    def _get_base_queryset() -> QuerySet[JournalEntry]:
        """Base queryset with annotations and prefetches (shared with the FilterSet, #3287)."""
        return base_entries_queryset()

    @staticmethod
    def _get_entry_for_response(pk: int) -> JournalEntry:
        """Re-fetch an entry with relations needed for detail serialization."""
        return (
            JournalEntry.objects.select_related("author__character")
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

    def _get_character_sheet(self, request: Request) -> CharacterSheet | None:
        """Get the CharacterSheet for the requesting user's character."""
        character = self._get_character(request)
        if not character:
            return None
        try:
            return character.sheet_data
        except CharacterSheet.DoesNotExist:
            return None

    def get_queryset(self) -> QuerySet[JournalEntry]:
        """The public feed queryset ``filter_queryset()`` (author/tag/deceased) builds on.

        Public entries plus ones revealed by an estate settlement (#3287 Decision 2) — a
        reveal never flips ``is_public``. Blocked/muted authors excluded (#2996 Decision 2).
        ``?deceased=`` (``JournalEntryFilter.filter_deceased``) replaces this queryset
        outright rather than narrowing it — the bequest corpus is a different shape (the
        deceased's non-sealed private+public entries), so this restriction is moot for that
        branch but harmless to compute either way (querysets are lazy).
        """
        queryset = self._get_base_queryset().filter(
            Q(is_public=True) | Q(revealed_at__isnull=False)
        )
        return exclude_blocked_and_muted_authors(queryset, viewer_account=self.request.user)

    def list(self, request: Request) -> Response:
        """
        List public journal entries, or (with ``?deceased=``) a bequeathed corpus.

        Supports query params (all handled by ``JournalEntryFilter``):
        - ?author=<character_id> — filter by author
        - ?tag=<tag_name> — filter by tag name
        - ?deceased=<character_sheet_id> — browse a deceased sheet's non-sealed private
          entries, ONLY when the caller holds a ``JournalBequestGrant`` for that sheet
          (#3287 Decision 3, gated in ``JournalEntryFilter.filter_deceased`` per
          ``tools/lint_use_filterset.py``). Empty when no grant exists — never a permission
          error, so a probing id can't confirm whether a grant exists for someone else.

        See ``get_queryset()`` for the public-feed contract (revealed entries, block/mute).
        """
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = JournalEntryListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        return Response(JournalEntryListSerializer(queryset, many=True).data)

    @action(detail=False, methods=["get"])
    def mine(self, request: Request) -> Response:
        """List the requesting character's own entries (including private)."""
        sheet = self._get_character_sheet(request)
        if not sheet:
            return Response(
                {"detail": "No character found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        queryset = self._get_base_queryset().filter(author=sheet)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = JournalEntryListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        return Response(JournalEntryListSerializer(queryset, many=True).data)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """
        Retrieve a single journal entry.

        Visible when: public, revealed by an estate settlement, authored by the caller, or
        (#3287 Decision 3) the caller holds a bequest grant over the author's writings and
        this entry's effective disposition isn't SEAL.
        """
        try:
            entry = (
                JournalEntry.objects.select_related("author__character")
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
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        sheet = self._get_character_sheet(request)
        publicly_visible = entry.is_public or entry.revealed_at is not None
        if not publicly_visible:
            is_own = sheet is not None and entry.author_id == sheet.pk
            if not is_own and not entry_visible_via_bequest(entry, sheet):
                return Response(
                    {"detail": "Not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # #2996 Decision 2 — mute: a response persists normally (write-then-filter, never
        # skip-the-write) but is excluded from the entry AUTHOR's own view of responses to
        # THEIR entry when the author has muted the responder's account. Only applies when the
        # requester IS the entry's author; any other viewer sees the full response list.
        if sheet is not None and sheet.pk == entry.author_id and entry.cached_responses:
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

        serializer = JournalEntryDetailSerializer(entry)
        return Response(serializer.data)

    def create(self, request: Request) -> Response:
        """Create a new journal entry."""
        character = self._get_character(request)
        if not character:
            return Response(
                {"detail": "No character found."},
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
        )
        if not result.success:
            return Response(
                {"detail": result.message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        entry = self._get_entry_for_response(result.data["entry_id"])
        return Response(
            JournalEntryDetailSerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        """Edit an existing journal entry (owner only)."""
        character = self._get_character(request)
        if not character:
            return Response(
                {"detail": "No character found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            sheet = character.sheet_data
        except CharacterSheet.DoesNotExist:
            return Response(
                {"detail": "No character found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            entry = JournalEntry.objects.get(pk=pk, author_id=sheet.pk)
        except JournalEntry.DoesNotExist:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = JournalEntryEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = get_action("edit_journal_entry").run(
            actor=character,
            entry=entry,
            title=serializer.validated_data.get("title"),
            body=serializer.validated_data.get("body"),
            posthumous_override=serializer.validated_data.get("posthumous_override"),
        )
        if not result.success:
            return Response(
                {"detail": result.message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = self._get_entry_for_response(result.data["entry_id"])
        return Response(JournalEntryDetailSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def respond(self, request: Request, pk: str | None = None) -> Response:
        """Create a praise or retort response to a journal entry."""
        character = self._get_character(request)
        if not character:
            return Response(
                {"detail": "No character found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            character.sheet_data  # noqa: B018
        except CharacterSheet.DoesNotExist:
            return Response(
                {"detail": "No character found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            parent = JournalEntry.objects.select_related("author").get(pk=pk)
        except JournalEntry.DoesNotExist:
            return Response(
                {"detail": "Not found."},
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
            JournalEntryDetailSerializer(response_entry).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get", "patch"])
    def disposition(self, request: Request) -> Response:
        """Read or set the caller's sheet-level default posthumous journal disposition.

        GET returns the current default; PATCH sets it via ``set_journal_disposition``
        (#3287) — the same seam ``journal disposition sheet=<...>`` uses on telnet.
        """
        sheet = self._get_character_sheet(request)
        if not sheet:
            return Response(
                {"detail": "No character found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == "GET":
            return Response(
                {"posthumous_journal_disposition": sheet.posthumous_journal_disposition}
            )

        serializer = JournalDispositionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        character = self._get_character(request)
        result = get_action("set_journal_disposition").run(
            actor=character,
            disposition=serializer.validated_data["disposition"],
        )
        if not result.success:
            return Response(
                {"detail": result.message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"posthumous_journal_disposition": result.data["disposition"]})
