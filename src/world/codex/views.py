"""
Codex System Views

API viewsets for browsing codex entries with visibility control.

Visibility model: anonymous visitors see ``is_public`` entries only.
Authenticated players see public entries plus the union of what all their
characters know; ``?character=<roster_entry_id>`` narrows the knowledge
scope to one of the account's characters. Categories and subjects are pure
taxonomy with no visibility of their own, so any container whose subtree
holds no visible entry is hidden outright -- subject descriptions are prose,
and prose nobody can contextualize with entries must not become the public
face of a topic (nor leak the existence of an all-secret branch).
"""

from django.db.models import Count, Exists, OuterRef, Q
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
from world.codex.types import CharacterKnowledge
from world.roster.models import RosterEntry


def _subjects_with_visible_entries(visible_entry_ids: set[int]) -> set[int]:
    """Return IDs of subjects with at least one visible entry in their subtree.

    A subject is visible when it, or any descendant subject, holds a visible
    entry. Computed in Python over the full (small, idmapper-cached) subject
    set: collect the subjects of the visible entries, then walk each parent
    chain upward so every ancestor stays visible too.
    """
    if not visible_entry_ids:
        return set()
    subjects_by_id = {subject.pk: subject for subject in CodexSubject.objects.all()}
    direct_ids = set(
        CodexEntry.objects.filter(id__in=visible_entry_ids).values_list("subject_id", flat=True)
    )
    visible: set[int] = set()
    for subject_id in direct_ids:
        current = subjects_by_id.get(subject_id)
        while current is not None and current.pk not in visible:
            visible.add(current.pk)
            current = subjects_by_id.get(current.parent_id) if current.parent_id else None
    return visible


class CodexVisibilityMixin:
    """Account-scoped visibility and knowledge resolution for codex viewsets.

    Replaces the old implicit first-roster-entry selection: knowledge is the
    union across every character the account can currently play, optionally
    narrowed by ``?character=<roster_entry_id>``. A ``character`` id that is
    not one of the account's own yields public-only visibility -- it can
    never widen into another player's knowledge.
    """

    _knowledge_map: dict[int, list[CharacterKnowledge]] | None = None
    _selected_entries: list[RosterEntry] | None = None
    _visible_entry_id_set: set[int] | None = None

    def _selected_roster_entries(self) -> list[RosterEntry]:
        """The account's playable roster entries, narrowed by ``?character=``."""
        if self._selected_entries is not None:
            return self._selected_entries
        self._selected_entries = self._resolve_selected_roster_entries()
        return self._selected_entries

    def _resolve_selected_roster_entries(self) -> list[RosterEntry]:
        request = self.request
        if not request.user.is_authenticated:
            return []
        try:
            player_data = request.user.player_data
        except AttributeError:
            return []
        characters = player_data.get_available_characters()
        if not characters:
            return []
        entries = list(
            RosterEntry.objects.filter(character_sheet__character__in=characters).select_related(
                "character_sheet__character"
            )
        )
        raw = request.query_params.get("character")  # noqa: USE_FILTERSET - knowledge scope, not a queryset filter
        if raw is None:
            return entries
        try:
            wanted = int(raw)
        except (TypeError, ValueError):
            return []
        return [entry for entry in entries if entry.pk == wanted]

    def _knowledge_by_entry(self) -> dict[int, list[CharacterKnowledge]]:
        """Map entry id -> selected characters' knowledge rows, one query."""
        if self._knowledge_map is not None:
            return self._knowledge_map
        knowledge: dict[int, list[CharacterKnowledge]] = {}
        roster_entries = self._selected_roster_entries()
        if roster_entries:
            rows = CharacterCodexKnowledge.objects.filter(
                roster_entry__in=roster_entries
            ).select_related("roster_entry__character_sheet__character")
            for row in rows:
                knowledge.setdefault(row.entry_id, []).append(
                    CharacterKnowledge(
                        roster_entry_id=row.roster_entry_id,
                        character_name=row.roster_entry.character_sheet.character.name,
                        status=row.status,
                        learning_progress=row.learning_progress,
                    )
                )
        for rows_for_entry in knowledge.values():
            rows_for_entry.sort(key=lambda item: item.character_name)
        self._knowledge_map = knowledge
        return knowledge

    def _visible_entry_ids(self) -> set[int]:
        """Public entries plus every entry a selected character has a row for."""
        if self._visible_entry_id_set is not None:
            return self._visible_entry_id_set
        public_ids = set(CodexEntry.objects.filter(is_public=True).values_list("id", flat=True))
        self._visible_entry_id_set = public_ids | set(self._knowledge_by_entry())
        return self._visible_entry_id_set

    def _visible_subject_ids(self) -> set[int]:
        return _subjects_with_visible_entries(self._visible_entry_ids())


class CodexCategoryViewSet(CodexVisibilityMixin, viewsets.ReadOnlyModelViewSet):
    """List and retrieve codex categories with a visible subtree."""

    serializer_class = CodexCategorySerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        """Only categories with at least one visible subject."""
        visible_category_ids = set(
            CodexSubject.objects.filter(
                parent=None, id__in=self._visible_subject_ids()
            ).values_list("category_id", flat=True)
        )
        return CodexCategory.objects.filter(id__in=visible_category_ids).order_by(
            "display_order", "name"
        )

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """Return visible categories with their visible top-level subjects.

        Children are loaded on demand via SubjectViewSet's ``children``
        action. This avoids deep nested prefetches that perform poorly.
        """
        visible_entry_ids = self._visible_entry_ids()
        visible_subject_ids = self._visible_subject_ids()

        # Two flat queries (categories + top-level subjects with annotation),
        # grouped in Python via the serializer context.
        # We avoid Prefetch(to_attr=...) here because CodexCategory is a
        # SharedMemoryModel: a `to_attr` set during one request persists on
        # the cached instance, and Django's prefetch_related skips re-fetching
        # when the attribute already exists, leaking annotation values across
        # requests with different visibility sets.
        top_subjects = (
            CodexSubject.objects.filter(parent=None, id__in=visible_subject_ids)
            .annotate(
                has_children=Exists(
                    CodexSubject.objects.filter(parent=OuterRef("pk"), id__in=visible_subject_ids)
                ),
                entry_count=Count(
                    "entries",
                    filter=Q(entries__id__in=visible_entry_ids),
                ),
            )
            .order_by("display_order", "name")
        )
        subjects_by_category: dict[int, list[CodexSubject]] = {}
        for subject in top_subjects:
            subjects_by_category.setdefault(subject.category_id, []).append(subject)

        categories = [
            category
            for category in CodexCategory.objects.order_by("display_order", "name")
            if category.id in subjects_by_category
        ]
        serializer = CodexCategoryTreeSerializer(
            categories,
            many=True,
            context={
                "visible_entry_ids": visible_entry_ids,
                "subjects_by_category": subjects_by_category,
            },
        )
        return Response(serializer.data)


class CodexSubjectViewSet(CodexVisibilityMixin, viewsets.ReadOnlyModelViewSet):
    """List and retrieve codex subjects with a visible subtree.

    A subject whose subtree holds no visible entry 404s on direct retrieve
    too -- its description must not be readable by probing ids.
    """

    serializer_class = CodexSubjectSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["category", "parent"]
    pagination_class = None

    def get_queryset(self):
        return CodexSubject.objects.select_related("category", "parent", "breadcrumb_cache").filter(
            id__in=self._visible_subject_ids()
        )

    @action(detail=True, methods=["get"])
    def children(self, request, pk=None):
        """Return visible children of a subject with has_children/entry_count.

        Used for lazy-loading tree expansion in the UI.
        """
        subject = self.get_object()
        visible_entry_ids = self._visible_entry_ids()
        visible_subject_ids = self._visible_subject_ids()

        children = (
            CodexSubject.objects.filter(parent=subject, id__in=visible_subject_ids)
            .annotate(
                has_children=Exists(
                    CodexSubject.objects.filter(parent=OuterRef("pk"), id__in=visible_subject_ids)
                ),
                entry_count=Count(
                    "entries",
                    filter=Q(entries__id__in=visible_entry_ids),
                ),
            )
            .order_by("display_order", "name")
        )

        serializer = CodexSubjectTreeSerializer(
            children, many=True, context={"visible_entry_ids": visible_entry_ids}
        )
        return Response(serializer.data)


class CodexEntryViewSet(CodexVisibilityMixin, viewsets.ReadOnlyModelViewSet):
    """List and retrieve codex entries with visibility control."""

    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CodexEntryFilter
    # Entries are filtered by visibility and limited, so pagination is not needed for browse UI
    pagination_class = None

    def get_queryset(self):
        """Return only entries visible to the selected characters."""
        return CodexEntry.objects.select_related(
            "subject",
            "subject__category",
            "subject__breadcrumb_cache",
        ).filter(id__in=self._visible_entry_ids())

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CodexEntryDetailSerializer
        return CodexEntryListSerializer

    def get_serializer_context(self):
        """Pass the knowledge map and reader characters to the serializers."""
        context = super().get_serializer_context()
        context["knowledge_by_entry"] = self._knowledge_by_entry()
        context["roster_entries"] = self._selected_roster_entries()
        return context
