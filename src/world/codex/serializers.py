"""
Codex System Serializers

DRF serializers for codex models with visibility-aware entry serialization.
"""

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

    def get_path(self, obj: CodexSubject) -> list[str]:
        """Return the full path from category to this subject."""
        path = [obj.name]
        current = obj.parent
        while current:
            path.insert(0, current.name)
            current = current.parent
        path.insert(0, obj.category.name)
        return path


class CodexSubjectTreeSerializer(serializers.ModelSerializer):
    """Recursive serializer for building subject tree."""

    children = serializers.SerializerMethodField()
    entry_count = serializers.SerializerMethodField()

    class Meta:
        model = CodexSubject
        fields = ["id", "name", "description", "display_order", "children", "entry_count"]

    def get_children(self, obj: CodexSubject) -> list[dict]:
        children = obj.children.all().order_by("display_order", "name")
        return CodexSubjectTreeSerializer(children, many=True, context=self.context).data

    def get_entry_count(self, obj: CodexSubject) -> int:
        """Count visible entries for this subject."""
        # Context should contain 'visible_entry_ids' set by the view
        visible_ids = self.context.get("visible_entry_ids", set())
        return obj.entries.filter(id__in=visible_ids).count()


class CodexEntryListSerializer(serializers.ModelSerializer):
    """Light serializer for entry lists."""

    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_path = serializers.SerializerMethodField()
    knowledge_status = serializers.SerializerMethodField()

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

    def get_subject_path(self, obj: CodexEntry) -> list[str]:
        path = [obj.subject.name]
        current = obj.subject.parent
        while current:
            path.insert(0, current.name)
            current = current.parent
        path.insert(0, obj.subject.category.name)
        return path

    def get_knowledge_status(self, obj: CodexEntry) -> str | None:
        """Return knowledge status for authenticated user's character."""
        knowledge_map = self.context.get("knowledge_map", {})
        return knowledge_map.get(obj.id)


class CodexEntryDetailSerializer(serializers.ModelSerializer):
    """Full serializer for entry detail view."""

    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_path = serializers.SerializerMethodField()
    knowledge_status = serializers.SerializerMethodField()
    research_progress = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()

    class Meta:
        model = CodexEntry
        fields = [
            "id",
            "name",
            "summary",
            "content",
            "is_public",
            "subject",
            "subject_name",
            "subject_path",
            "display_order",
            "learn_threshold",
            "knowledge_status",
            "research_progress",
        ]

    def get_subject_path(self, obj: CodexEntry) -> list[str]:
        path = [obj.subject.name]
        current = obj.subject.parent
        while current:
            path.insert(0, current.name)
            current = current.parent
        path.insert(0, obj.subject.category.name)
        return path

    def get_knowledge_status(self, obj: CodexEntry) -> str | None:
        knowledge_map = self.context.get("knowledge_map", {})
        return knowledge_map.get(obj.id)

    def get_research_progress(self, obj: CodexEntry) -> int | None:
        progress_map = self.context.get("progress_map", {})
        return progress_map.get(obj.id)

    def get_content(self, obj: CodexEntry) -> str | None:
        """Return content only if public or KNOWN."""
        if obj.is_public:
            return obj.content
        knowledge_map = self.context.get("knowledge_map", {})
        status = knowledge_map.get(obj.id)
        if status == CharacterCodexKnowledge.Status.KNOWN:
            return obj.content
        return None  # UNCOVERED shows summary only


class CodexClueSerializer(serializers.ModelSerializer):
    entry_name = serializers.CharField(source="entry.name", read_only=True)

    class Meta:
        model = CodexClue
        fields = ["id", "name", "description", "research_value", "entry", "entry_name"]
