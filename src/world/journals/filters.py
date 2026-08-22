"""Filters for the journal system API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import django_filters
from django_filters.rest_framework import DjangoFilterBackend

from world.journals.models import JournalEntry
from world.journals.services import (
    base_entries_queryset,
    has_journal_bequest_grant,
    sealed_effective_q,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


class JournalFilterBackend(DjangoFilterBackend):
    """``DjangoFilterBackend`` that also hands the view instance to the FilterSet.

    The stock backend's ``get_filterset_kwargs`` only passes ``data``/``queryset``/``request``
    (see ``django_filters.rest_framework.backends.DjangoFilterBackend``) — no ``view``. The
    ``deceased`` filter (#3287) needs the SAME viewer-resolution path every other
    ``JournalEntryViewSet`` method uses (``CharacterContextMixin._get_character`` via
    ``get_character_sheet``), not an independent re-implementation, so that mocking
    ``JournalEntryViewSet._get_character`` in tests (the established pattern throughout this
    app's test suite) also governs the FilterSet's resolution — a request-only duplicate
    silently diverged from that mock and returned an empty corpus.
    """

    def get_filterset_kwargs(
        self, request: Request, queryset: QuerySet[JournalEntry], view: Any
    ) -> dict:
        kwargs = super().get_filterset_kwargs(request, queryset, view)
        kwargs["view"] = view
        return kwargs


class JournalEntryFilter(django_filters.FilterSet):
    """Filter for JournalEntry list views."""

    author = django_filters.NumberFilter(field_name="author_id")
    tag = django_filters.CharFilter(field_name="tags__name")
    # Browse a deceased sheet's bequeathed corpus (#3287) instead of the public feed. Gated
    # here — not read from request.query_params in the view — per
    # tools/lint_use_filterset.py's USE_FILTERSET rule: the permission check needs the
    # viewer's own character, which a plain field lookup cannot express. Declared last (and
    # in Meta.fields last) so it wins if ever combined with author/tag — an untested
    # combination that mirrors the pre-refactor behavior of dispatching to an entirely
    # separate query branch.
    deceased = django_filters.NumberFilter(method="filter_deceased")

    class Meta:
        model = JournalEntry
        fields = ["author", "tag", "deceased"]

    def __init__(self, *args: Any, view: Any = None, **kwargs: Any) -> None:
        """Accept the view instance (see ``JournalFilterBackend``) for ``filter_deceased``."""
        self.view = view
        super().__init__(*args, **kwargs)

    def filter_deceased(
        self, queryset: QuerySet[JournalEntry], name: str, value: int
    ) -> QuerySet[JournalEntry]:
        """Gate ``?deceased=<sheet_id>`` on a ``JournalBequestGrant`` (#3287 Decision 3).

        Replaces ``queryset`` outright — a grant unlocks the deceased's full non-sealed
        private+public corpus, a different shape than the public feed ``queryset`` already
        carries (public-only, block/mute-excluded). Empty — never an error — when the viewer
        has no active character or no grant for this sheet, so a probing id can't confirm a
        grant exists for someone else.
        """
        del queryset, name  # the bequest corpus ignores the incoming public-feed queryset
        sheet = self.view.get_character_sheet(self.request) if self.view is not None else None
        if sheet is None or not has_journal_bequest_grant(
            recipient_sheet=sheet, deceased_sheet_id=value
        ):
            return JournalEntry.objects.none()
        return base_entries_queryset().filter(author_id=value).exclude(sealed_effective_q())
