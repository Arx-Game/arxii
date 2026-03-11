"""API views for the journal system."""

from __future__ import annotations

from django.db.models import Count, QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from web.api.mixins import CharacterContextMixin
from world.character_sheets.models import CharacterSheet
from world.journals.models import JournalEntry
from world.journals.serializers import (
    JournalEntryCreateSerializer,
    JournalEntryDetailSerializer,
    JournalEntryEditSerializer,
    JournalEntryListSerializer,
    JournalResponseCreateSerializer,
)
from world.journals.services import (
    create_journal_entry,
    create_journal_response,
    edit_journal_entry,
)
from world.journals.types import JournalError


class JournalEntryPagination(PageNumberPagination):
    """Pagination for journal entries."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class JournalEntryViewSet(CharacterContextMixin, viewsets.GenericViewSet):
    """
    ViewSet for journal entries.

    Endpoints:
    - GET  /entries/        — list public entries (supports ?author, ?tag filters)
    - GET  /entries/mine/   — list own entries including private
    - GET  /entries/<id>/   — retrieve single entry
    - POST /entries/        — create a new entry
    - POST /entries/<id>/respond/ — create praise/retort response
    """

    permission_classes = [IsAuthenticated]
    pagination_class = JournalEntryPagination

    @staticmethod
    def _get_base_queryset() -> QuerySet[JournalEntry]:
        """Base queryset with annotations and prefetches."""
        return (
            JournalEntry.objects.select_related("author__character")
            .prefetch_related("tags")
            .annotate(response_count=Count("responses"))
            .order_by("-created_at")
            .distinct()
        )

    @staticmethod
    def _get_entry_for_response(pk: int) -> JournalEntry:
        """Re-fetch an entry with relations needed for detail serialization."""
        return (
            JournalEntry.objects.select_related("author__character")
            .prefetch_related("tags", "responses__author__character")
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

    def list(self, request: Request) -> Response:
        """
        List public journal entries.

        Supports query params:
        - ?author=<character_id> — filter by author
        - ?tag=<tag_name> — filter by tag name
        """
        queryset = self._get_base_queryset().filter(is_public=True)

        author_id = request.query_params.get("author")
        if author_id:
            queryset = queryset.filter(author_id=author_id)

        tag = request.query_params.get("tag")
        if tag:
            queryset = queryset.filter(tags__name=tag)

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

        Public entries are visible to all authenticated users.
        Private entries are only visible to their author.
        """
        try:
            entry = (
                JournalEntry.objects.select_related("author__character")
                .prefetch_related("tags", "responses__author__character")
                .get(pk=pk)
            )
        except JournalEntry.DoesNotExist:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not entry.is_public:
            sheet = self._get_character_sheet(request)
            if not sheet or entry.author_id != sheet.pk:
                return Response(
                    {"detail": "Not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        serializer = JournalEntryDetailSerializer(entry)
        return Response(serializer.data)

    def create(self, request: Request) -> Response:
        """Create a new journal entry."""
        sheet = self._get_character_sheet(request)
        if not sheet:
            return Response(
                {"detail": "No character found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = JournalEntryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        entry = create_journal_entry(
            author=sheet,
            title=serializer.validated_data["title"],
            body=serializer.validated_data["body"],
            is_public=serializer.validated_data["is_public"],
            tags=serializer.validated_data.get("tags"),
        )

        entry = self._get_entry_for_response(entry.pk)
        return Response(
            JournalEntryDetailSerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        """Edit an existing journal entry (owner only)."""
        sheet = self._get_character_sheet(request)
        if not sheet:
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

        try:
            updated = edit_journal_entry(
                entry=entry,
                title=serializer.validated_data.get("title"),
                body=serializer.validated_data.get("body"),
            )
        except JournalError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = self._get_entry_for_response(updated.pk)
        return Response(JournalEntryDetailSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def respond(self, request: Request, pk: str | None = None) -> Response:
        """Create a praise or retort response to a journal entry."""
        sheet = self._get_character_sheet(request)
        if not sheet:
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

        try:
            response_entry = create_journal_response(
                author=sheet,
                parent=parent,
                response_type=serializer.validated_data["response_type"],
                title=serializer.validated_data["title"],
                body=serializer.validated_data["body"],
            )
        except JournalError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_entry = self._get_entry_for_response(response_entry.pk)
        return Response(
            JournalEntryDetailSerializer(response_entry).data,
            status=status.HTTP_201_CREATED,
        )
