"""
Codex System Views

API viewsets for browsing codex entries with visibility control.
Public entries visible to all, restricted entries require character knowledge.
"""

from django.db.models import CharField, Exists, IntegerField, OuterRef, Prefetch, Q, Subquery, Value
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from world.codex.filters import CodexEntryFilter
from world.codex.models import (
    CharacterCodexKnowledge,
    CodexCategory,
    CodexEntry,
    CodexSubject,
)
from world.codex.serializers import (
    CodexCategorySerializer,
    CodexCategoryTreeSerializer,
    CodexEntryDetailSerializer,
    CodexEntryListSerializer,
    CodexSubjectSerializer,
    CodexSubjectTreeSerializer,
)
from world.roster.models import RosterEntry


class CodexCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve codex categories."""

    queryset = CodexCategory.objects.all()
    serializer_class = CodexCategorySerializer
    permission_classes = [AllowAny]
    pagination_class = None

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """Return categories with top-level subjects only.

        Children are loaded on demand via SubjectViewSet with ?parent= filter.
        This avoids deep nested prefetches that perform poorly.
        """
        visible_entry_ids = self._get_visible_entry_ids(request)

        # Only prefetch top-level subjects - no nested children
        categories = CodexCategory.objects.prefetch_related(
            Prefetch(
                "subjects",
                queryset=CodexSubject.objects.filter(parent=None)
                .annotate(has_children=Exists(CodexSubject.objects.filter(parent=OuterRef("pk"))))
                .order_by("display_order", "name"),
                to_attr="cached_top_subjects",
            )
        )

        serializer = CodexCategoryTreeSerializer(
            categories, many=True, context={"visible_entry_ids": visible_entry_ids}
        )
        return Response(serializer.data)

    def _get_visible_entry_ids(self, request) -> set[int]:
        """Get IDs of entries visible to current user."""
        public_ids = set(CodexEntry.objects.filter(is_public=True).values_list("id", flat=True))

        if not request.user.is_authenticated:
            return public_ids

        # Get active character's knowledge
        roster_entry = self._get_active_roster_entry(request)
        if not roster_entry:
            return public_ids

        known_ids = set(
            CharacterCodexKnowledge.objects.filter(roster_entry=roster_entry).values_list(
                "entry_id", flat=True
            )
        )
        return public_ids | known_ids

    def _get_active_roster_entry(self, request):
        """Get active character's roster entry from session or default."""
        # TODO: Integrate with session character selection
        # For now, return first roster entry for the account
        return RosterEntry.objects.filter(
            tenures__player_data__account=request.user, tenures__end_date__isnull=True
        ).first()


class CodexSubjectViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve codex subjects."""

    queryset = CodexSubject.objects.select_related("category", "parent", "breadcrumb_cache").all()
    serializer_class = CodexSubjectSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["category", "parent"]
    pagination_class = None

    @action(detail=True, methods=["get"])
    def children(self, request, pk=None):
        """Return children of a subject with has_children and entry_count.

        Used for lazy-loading tree expansion in the UI.
        """
        subject = self.get_object()
        visible_entry_ids = self._get_visible_entry_ids(request)

        children = (
            CodexSubject.objects.filter(parent=subject)
            .annotate(has_children=Exists(CodexSubject.objects.filter(parent=OuterRef("pk"))))
            .order_by("display_order", "name")
        )

        serializer = CodexSubjectTreeSerializer(
            children, many=True, context={"visible_entry_ids": visible_entry_ids}
        )
        return Response(serializer.data)

    def _get_visible_entry_ids(self, request) -> set[int]:
        """Get IDs of entries visible to current user."""
        public_ids = set(CodexEntry.objects.filter(is_public=True).values_list("id", flat=True))

        if not request.user.is_authenticated:
            return public_ids

        roster_entry = self._get_active_roster_entry(request)
        if not roster_entry:
            return public_ids

        known_ids = set(
            CharacterCodexKnowledge.objects.filter(roster_entry=roster_entry).values_list(
                "entry_id", flat=True
            )
        )
        return public_ids | known_ids

    def _get_active_roster_entry(self, request):
        """Get active character's roster entry from session or default."""
        return RosterEntry.objects.filter(
            tenures__player_data__account=request.user, tenures__end_date__isnull=True
        ).first()


class CodexEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve codex entries with visibility control."""

    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CodexEntryFilter
    # Entries are filtered by visibility and limited, so pagination is not needed for browse UI
    pagination_class = None

    def get_queryset(self):
        """Return only visible entries with knowledge annotations.

        Always annotates knowledge_status and research_progress so serializers
        can access them directly without getattr.
        """
        qs = CodexEntry.objects.select_related(
            "subject",
            "subject__category",
            "subject__breadcrumb_cache",
        )

        roster_entry = self._get_active_roster_entry()

        # Always annotate - NULL for anonymous/no character
        if roster_entry:
            knowledge_subquery = CharacterCodexKnowledge.objects.filter(
                entry=OuterRef("pk"),
                roster_entry=roster_entry,
            )
            qs = qs.annotate(
                knowledge_status=Subquery(knowledge_subquery.values("status")[:1]),
                research_progress=Subquery(knowledge_subquery.values("learning_progress")[:1]),
            )
        else:
            # Annotate with NULL so the attribute always exists
            qs = qs.annotate(
                knowledge_status=Value(None, output_field=CharField()),
                research_progress=Value(None, output_field=IntegerField()),
            )

        # Anonymous users see only public entries
        if not self.request.user.is_authenticated or not roster_entry:
            return qs.filter(is_public=True)

        # Filter to visible entries (public or known by character)
        known_entry_ids = CharacterCodexKnowledge.objects.filter(
            roster_entry=roster_entry
        ).values_list("entry_id", flat=True)
        return qs.filter(Q(is_public=True) | Q(id__in=known_entry_ids))

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CodexEntryDetailSerializer
        return CodexEntryListSerializer

    def _get_active_roster_entry(self):
        if not self.request.user.is_authenticated:
            return None
        return RosterEntry.objects.filter(
            tenures__player_data__account=self.request.user, tenures__end_date__isnull=True
        ).first()
