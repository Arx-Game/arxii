"""
Codex System Serializers

DRF serializers for codex models with visibility-aware entry serialization.
"""

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from world.codex.constants import CodexKnowledgeStatus
from world.codex.models import (
    CodexCategory,
    CodexEntry,
    CodexSubject,
)
from world.codex.services import resolve_codex_links
from world.codex.types import CharacterKnowledge


class CodexCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CodexCategory
        fields = ["id", "name", "description", "display_order"]


class CodexSubjectSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, allow_null=True)
    path = serializers.SerializerMethodField()

    class Meta:
        model = CodexSubject
        fields = [
            "id",
            "name",
            "description",
            "display_order",
            "category",
            "category_name",
            "parent",
            "parent_name",
            "path",
        ]

    def get_path(self, obj: CodexSubject) -> list[dict]:
        """Return the full path with IDs, preferring materialized view cache."""
        try:
            return obj.breadcrumb_cache.breadcrumb_path
        except ObjectDoesNotExist:
            return obj.breadcrumb_path


class CodexSubjectTreeSerializer(serializers.ModelSerializer):
    """Serializer for subject tree nodes (flat, no recursion).

    Returns has_children flag instead of nested children array.
    Children are loaded on demand via SubjectViewSet with ?parent= filter.

    `entry_count` is read from a queryset annotation applied upstream by the
    view (filtered Count of visible entries). Avoids per-row N+1 queries.
    """

    has_children = serializers.BooleanField(read_only=True)
    entry_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CodexSubject
        fields = ["id", "name", "has_children", "entry_count"]


class CodexCategoryTreeSerializer(serializers.ModelSerializer):
    """Serializer for category tree with nested subjects.

    Uses prefetched top-level subjects from view.
    """

    subjects = serializers.SerializerMethodField()

    class Meta:
        model = CodexCategory
        fields = ["id", "name", "description", "subjects"]

    def get_subjects(self, obj: CodexCategory) -> list[dict]:
        """Get top-level subjects via the view's request-scoped grouping.

        The view fetches subjects (with annotations) in a flat query and
        groups them by category_id into ``subjects_by_category``. We can't
        attach prefetched data to the CodexCategory instance because it's a
        SharedMemoryModel and the attribute would leak across requests.
        """
        subjects_by_category = self.context.get("subjects_by_category", {})
        top_subjects = subjects_by_category.get(obj.id, [])
        return CodexSubjectTreeSerializer(top_subjects, many=True, context=self.context).data


class EntryKnowledgeMixin(serializers.Serializer):
    """Per-character knowledge fields, read from the view's knowledge map.

    The view builds ``context["knowledge_by_entry"]`` (entry id -> list of
    :class:`~world.codex.types.CharacterKnowledge` for the reader's selected
    characters) in one query; these fields aggregate it. ``knowledge_status``
    is the best status across the selected characters, ``research_progress``
    the furthest progress, and ``known_by`` the full per-character breakdown.
    """

    knowledge_status = serializers.SerializerMethodField()
    research_progress = serializers.SerializerMethodField()
    known_by = serializers.SerializerMethodField()
    perspective_of = serializers.SerializerMethodField()
    also_filed_under = serializers.SerializerMethodField()

    def get_also_filed_under(self, obj: CodexEntry) -> list[dict]:
        """Other subjects this entry is cross-listed under, via a filing.

        Reads ``context["filings_by_entry"]`` (the view builds it in one
        flat query, joined to each filed subject and that subject's
        breadcrumb cache), so this adds no query per entry. Each item
        mirrors the shape of a breadcrumb entry: the filed subject's id,
        name, and its own breadcrumb path, so the frontend can link
        straight to that listing.
        """
        items = []
        for filing in self.context.get("filings_by_entry", {}).get(obj.id, []):
            subject = filing.subject
            try:
                breadcrumb_path = subject.breadcrumb_cache.breadcrumb_path
            except ObjectDoesNotExist:
                breadcrumb_path = subject.breadcrumb_path
            items.append(
                {
                    "subject_id": subject.pk,
                    "name": subject.name,
                    "breadcrumb_path": breadcrumb_path,
                }
            )
        return items

    def get_perspective_of(self, obj: CodexEntry) -> str | None:
        """Name of the culture whose take this entry is; None for canon entries.

        Reads the queryset annotation; falls back to None where a caller
        serializes without it (e.g. featured lore).
        """
        return getattr(obj, "perspective_of", None)  # noqa: GETATTR_LITERAL - may be unannotated

    def _entry_knowledge(self, obj: CodexEntry) -> list[CharacterKnowledge]:
        return self.context.get("knowledge_by_entry", {}).get(obj.id, [])

    def get_knowledge_status(self, obj: CodexEntry) -> str | None:
        statuses = {item.status for item in self._entry_knowledge(obj)}
        if CodexKnowledgeStatus.KNOWN in statuses:
            return CodexKnowledgeStatus.KNOWN
        if CodexKnowledgeStatus.UNCOVERED in statuses:
            return CodexKnowledgeStatus.UNCOVERED
        return None

    def get_research_progress(self, obj: CodexEntry) -> int | None:
        progresses = [item.learning_progress for item in self._entry_knowledge(obj)]
        return max(progresses) if progresses else None

    def get_known_by(self, obj: CodexEntry) -> list[dict]:
        return [
            {
                "roster_entry_id": item.roster_entry_id,
                "character_name": item.character_name,
                "status": item.status,
                "research_progress": item.learning_progress,
            }
            for item in self._entry_knowledge(obj)
        ]


class CodexEntryListSerializer(EntryKnowledgeMixin, serializers.ModelSerializer):
    """Light serializer for entry lists."""

    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_path = serializers.SerializerMethodField()
    art_url = serializers.SerializerMethodField()

    class Meta:
        model = CodexEntry
        fields = [
            "id",
            "name",
            "summary",
            "is_public",
            "is_featured",
            "featured_order",
            "subject",
            "subject_name",
            "subject_path",
            "display_order",
            "knowledge_status",
            "known_by",
            "perspective_of",
            "also_filed_under",
            "art_url",
        ]

    def get_subject_path(self, obj: CodexEntry) -> list[dict]:
        """Return the subject path with IDs for clickable breadcrumb navigation."""
        try:
            return obj.subject.breadcrumb_cache.breadcrumb_path
        except ObjectDoesNotExist:
            return obj.subject.breadcrumb_path

    def get_art_url(self, obj: CodexEntry) -> str | None:
        return obj.art.cloudinary_url if obj.art_id else None


class CodexEntryDetailSerializer(EntryKnowledgeMixin, serializers.ModelSerializer):
    """Full serializer for entry detail view."""

    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_path = serializers.SerializerMethodField()
    lore_content = serializers.SerializerMethodField()
    mechanics_content = serializers.SerializerMethodField()
    lore_links = serializers.SerializerMethodField()
    mechanics_links = serializers.SerializerMethodField()
    art_url = serializers.SerializerMethodField()

    class Meta:
        model = CodexEntry
        fields = [
            "id",
            "name",
            "summary",
            "lore_content",
            "mechanics_content",
            "lore_links",
            "mechanics_links",
            "is_public",
            "is_featured",
            "featured_order",
            "subject",
            "subject_name",
            "subject_path",
            "display_order",
            "learn_threshold",
            "knowledge_status",
            "research_progress",
            "known_by",
            "perspective_of",
            "also_filed_under",
            "art_url",
        ]

    def get_subject_path(self, obj: CodexEntry) -> list[dict]:
        """Return the subject path with IDs for clickable breadcrumb navigation."""
        try:
            return obj.subject.breadcrumb_cache.breadcrumb_path
        except ObjectDoesNotExist:
            return obj.subject.breadcrumb_path

    def _can_see_content(self, obj: CodexEntry) -> bool:
        """Check if full content should be visible to the user."""
        return obj.is_public or self.get_knowledge_status(obj) == CodexKnowledgeStatus.KNOWN

    def get_lore_content(self, obj: CodexEntry) -> str | None:
        """Return lore content only if public or KNOWN."""
        return obj.lore_content if self._can_see_content(obj) else None

    def get_mechanics_content(self, obj: CodexEntry) -> str | None:
        """Return mechanics content only if public or KNOWN."""
        return obj.mechanics_content if self._can_see_content(obj) else None

    def _get_links(self, obj: CodexEntry, content: str | None) -> list[dict]:
        """Resolve inline wikilinks if the reader can see the content."""
        if not self._can_see_content(obj) or not content:
            return []
        roster_entries = self.context.get("roster_entries", [])
        return resolve_codex_links(content, obj.subject, roster_entries)

    def get_lore_links(self, obj: CodexEntry) -> list[dict]:
        """Return resolved wikilinks from lore_content."""
        return self._get_links(obj, obj.lore_content)

    def get_mechanics_links(self, obj: CodexEntry) -> list[dict]:
        """Return resolved wikilinks from mechanics_content."""
        return self._get_links(obj, obj.mechanics_content)

    def get_art_url(self, obj: CodexEntry) -> str | None:
        return obj.art.cloudinary_url if obj.art_id else None
