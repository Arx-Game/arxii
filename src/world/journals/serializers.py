"""DRF serializers for the journal system."""

from rest_framework import serializers

from world.journals.constants import ResponseType
from world.journals.models import JournalEntry, JournalTag


class JournalTagSerializer(serializers.ModelSerializer):
    """Serializer for journal tags."""

    class Meta:
        model = JournalTag
        fields = ["id", "name"]
        read_only_fields = ["id"]


class JournalEntryListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for journal feed/list views."""

    author_name = serializers.CharField(source="author.character.db_key", read_only=True)
    tags = JournalTagSerializer(many=True, read_only=True)
    response_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "author",
            "author_name",
            "title",
            "is_public",
            "response_type",
            "parent",
            "created_at",
            "edited_at",
            "tags",
            "response_count",
        ]
        read_only_fields = fields


class JournalEntryDetailSerializer(serializers.ModelSerializer):
    """Full serializer for reading a single journal entry."""

    author_name = serializers.CharField(source="author.character.db_key", read_only=True)
    tags = JournalTagSerializer(many=True, read_only=True)
    responses = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "author",
            "author_name",
            "title",
            "body",
            "is_public",
            "response_type",
            "parent",
            "created_at",
            "edited_at",
            "tags",
            "responses",
        ]
        read_only_fields = fields

    def get_responses(self, obj: JournalEntry) -> list[dict]:
        """Return lightweight list of responses."""
        responses = sorted(obj.responses.all(), key=lambda r: r.created_at, reverse=True)
        return JournalEntryListSerializer(responses, many=True).data


class JournalEntryCreateSerializer(serializers.Serializer):
    """Serializer for creating a new journal entry."""

    title = serializers.CharField(max_length=200)
    body = serializers.CharField()
    is_public = serializers.BooleanField(default=False)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
    )


class JournalResponseCreateSerializer(serializers.Serializer):
    """Serializer for creating a praise or retort response."""

    title = serializers.CharField(max_length=200)
    body = serializers.CharField()
    response_type = serializers.ChoiceField(choices=ResponseType.choices)


class JournalEntryEditSerializer(serializers.Serializer):
    """Serializer for editing a journal entry."""

    title = serializers.CharField(max_length=200, required=False)
    body = serializers.CharField(required=False)
