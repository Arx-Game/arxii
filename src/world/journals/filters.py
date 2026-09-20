"""Filters for the journal system API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import django_filters
from django_filters.rest_framework import DjangoFilterBackend

# The plain ``django_filters.BooleanFilter`` defaults to Django's ``NullBooleanSelect``
# widget, which only recognizes "true"/"false"/"2"/"3" — a JSON/JS-side "1"/"0" (what an
# API client naturally sends) parses to ``None`` and the filter silently no-ops. The REST
# variant defaults to django-filter's own ``BooleanWidget``, which also accepts "1"/"0".
from django_filters.rest_framework.filters import BooleanFilter as RestBooleanFilter

from world.journals.constants import INTRODUCTION_KINDS
from world.journals.models import JournalEntry
from world.journals.services import (
    base_entries_queryset,
    has_journal_bequest_grant,
    sealed_effective_q,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request

#: The Search filter's "Introductions" alias for ``INTRODUCTION_KINDS`` (#3941).
INTRODUCTION_KINDS_ALIAS = "introductions"


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
    writer = django_filters.CharFilter(
        field_name="author__character__db_key", lookup_expr="icontains"
    )
    about = django_filters.NumberFilter(field_name="about_id")
    kind = django_filters.CharFilter(method="filter_kind")
    post_mortem = RestBooleanFilter(field_name="revealed_at", lookup_expr="isnull", exclude=True)
    # The "Since your last visit" cut (#3941). The client names the moment: it sends back
    # the ``visited_at`` the stream's first response carried -- the mark as it was BEFORE
    # that request advanced it. A server-side ``since_visit=1`` flag cannot work, because
    # opening the stream stamps the mark to now, so by the time the reader presses the
    # option every entry is older than the mark and the cut is always empty.
    since = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gt")
    black_only = RestBooleanFilter(method="filter_black_only")
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
        fields = [
            "author",
            "tag",
            "writer",
            "about",
            "kind",
            "post_mortem",
            "since",
            "black_only",
            "deceased",
        ]

    def __init__(self, *args: Any, view: Any = None, **kwargs: Any) -> None:
        """Accept the view instance (see ``JournalFilterBackend``) for ``filter_deceased``."""
        self.view = view
        super().__init__(*args, **kwargs)

    def filter_kind(
        self, queryset: QuerySet[JournalEntry], name: str, value: str
    ) -> QuerySet[JournalEntry]:
        """``kind=<JournalKind>`` or the alias ``introductions`` (the three CG kinds)."""
        del name
        if value == INTRODUCTION_KINDS_ALIAS:
            return queryset.filter(kind__in=INTRODUCTION_KINDS)
        return queryset.filter(kind=value)

    def filter_black_only(
        self, queryset: QuerySet[JournalEntry], name: str, value: bool
    ) -> QuerySet[JournalEntry]:
        """Staff only: just the private entries. Silently ignored for everyone else."""
        del name
        if not value or not self.request.user.is_staff:
            return queryset
        return queryset.filter(is_public=False, revealed_at__isnull=True)

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
