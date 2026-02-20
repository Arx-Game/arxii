"""
Codex System Serializers

DRF serializers for codex models with visibility-aware entry serialization.
"""

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from world.codex.models import (
    CharacterCodexKnowledge,
    CodexCategory,
    CodexClue,
    CodexEntry,
    CodexSubject,
)


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
    """

    has_children = serializers.BooleanField(read_only=True)
    entry_count = serializers.SerializerMethodField()

    class Meta:
        model = CodexSubject
        fields = ["id", "name", "has_children", "entry_count"]

    def get_entry_count(self, obj: CodexSubject) -> int:
        """Count visible entries for this subject."""
        visible_ids = self.context.get("visible_entry_ids", set())
        return obj.entries.filter(id__in=visible_ids).count()


class CodexCategoryTreeSerializer(serializers.ModelSerializer):
    """Serializer for category tree with nested subjects.

    Uses prefetched top-level subjects from view.
    """

    subjects = serializers.SerializerMethodField()

    class Meta:
        model = CodexCategory
        fields = ["id", "name", "description", "subjects"]

    def get_subjects(self, obj: CodexCategory) -> list[dict]:
        """Get top-level subjects using prefetched data."""
        # Access prefetched subjects from view's Prefetch with to_attr
        if hasattr(obj, "cached_top_subjects"):
            top_subjects = obj.cached_top_subjects
        else:
            # Fallback if not prefetched (shouldn't happen in normal use)
            top_subjects = list(obj.subjects.filter(parent=None))
            top_subjects.sort(key=lambda x: (x.display_order, x.name))
        return CodexSubjectTreeSerializer(top_subjects, many=True, context=self.context).data


class CodexEntryListSerializer(serializers.ModelSerializer):
    """Light serializer for entry lists.

    Uses annotated fields from ViewSet queryset for knowledge data.
    """

    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_path = serializers.SerializerMethodField()
    # Read from Subquery annotation set by ViewSet
    knowledge_status = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = CodexEntry
        fields = [
            "id",
            "name",
            "summary",
            "is_public",
            "subject",
            "subject_name",
            "subject_path",
            "display_order",
            "knowledge_status",
        ]

    def get_subject_path(self, obj: CodexEntry) -> list[dict]:
        """Return the subject path with IDs for clickable breadcrumb navigation."""
        try:
            return obj.subject.breadcrumb_cache.breadcrumb_path
        except ObjectDoesNotExist:
            return obj.subject.breadcrumb_path


class CodexEntryDetailSerializer(serializers.ModelSerializer):
    """Full serializer for entry detail view.

    Uses annotated fields from ViewSet queryset for knowledge data.
    """

    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_path = serializers.SerializerMethodField()
    # Read from Subquery annotations set by ViewSet
    knowledge_status = serializers.CharField(read_only=True, allow_null=True)
    research_progress = serializers.IntegerField(read_only=True, allow_null=True)
    lore_content = serializers.SerializerMethodField()
    mechanics_content = serializers.SerializerMethodField()

    class Meta:
        model = CodexEntry
        fields = [
            "id",
            "name",
            "summary",
            "lore_content",
            "mechanics_content",
            "is_public",
            "subject",
            "subject_name",
            "subject_path",
            "display_order",
            "learn_threshold",
            "knowledge_status",
            "research_progress",
        ]

    def get_subject_path(self, obj: CodexEntry) -> list[dict]:
        """Return the subject path with IDs for clickable breadcrumb navigation."""
        try:
            return obj.subject.breadcrumb_cache.breadcrumb_path
        except ObjectDoesNotExist:
            return obj.subject.breadcrumb_path

    def _can_see_content(self, obj: CodexEntry) -> bool:
        """Check if full content should be visible to the user."""
        return obj.is_public or obj.knowledge_status == CharacterCodexKnowledge.Status.KNOWN

    def get_lore_content(self, obj: CodexEntry) -> str | None:
        """Return lore content only if public or KNOWN."""
        return obj.lore_content if self._can_see_content(obj) else None

    def get_mechanics_content(self, obj: CodexEntry) -> str | None:
        """Return mechanics content only if public or KNOWN."""
        return obj.mechanics_content if self._can_see_content(obj) else None


class CodexClueSerializer(serializers.ModelSerializer):
    entry_name = serializers.CharField(source="entry.name", read_only=True)

    class Meta:
        model = CodexClue
        fields = ["id", "name", "description", "research_value", "entry", "entry_name"]
