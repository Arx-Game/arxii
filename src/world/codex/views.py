"""
Codex System Views

API viewsets for browsing codex entries with visibility control.
Public entries visible to all, restricted entries require character knowledge.
"""

from django.db.models import OuterRef, Prefetch, Q, Subquery
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
        """Return full category/subject tree with entry counts.

        Uses bounded prefetch_related to load subject hierarchy efficiently.
        Limits depth to 4 levels (category + 3 subject levels).
        """
        visible_entry_ids = self._get_visible_entry_ids(request)

        # Prefetch top-level subjects with bounded depth for children
        # This pattern avoids N+1 queries while limiting recursion depth
        categories = CodexCategory.objects.prefetch_related(
            Prefetch(
                "subjects",
                queryset=CodexSubject.objects.filter(parent=None)
                .prefetch_related("children__children__children")
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

    queryset = CodexSubject.objects.select_related("category", "parent").all()
    serializer_class = CodexSubjectSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["category", "parent"]
    pagination_class = None


class CodexEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve codex entries with visibility control."""

    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CodexEntryFilter
    # Entries are filtered by visibility and limited, so pagination is not needed for browse UI
    pagination_class = None

    def get_queryset(self):
        """Return only visible entries with knowledge annotations.

        Uses Subquery annotations instead of context maps to avoid multiple
        queries and simplify serializer logic.
        """
        # Bounded select_related for path computation (category + 3 subject levels)
        qs = CodexEntry.objects.select_related(
            "subject",
            "subject__category",
            "subject__parent",
            "subject__parent__parent",
            "subject__parent__parent__parent",
        )

        roster_entry = self._get_active_roster_entry()

        # Anonymous users see only public entries
        if not self.request.user.is_authenticated or not roster_entry:
            return qs.filter(is_public=True)

        # Annotate with knowledge status and progress via Subquery
        knowledge_subquery = CharacterCodexKnowledge.objects.filter(
            entry=OuterRef("pk"),
            roster_entry=roster_entry,
        )
        qs = qs.annotate(
            knowledge_status=Subquery(knowledge_subquery.values("status")[:1]),
            research_progress=Subquery(knowledge_subquery.values("learning_progress")[:1]),
        )

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
