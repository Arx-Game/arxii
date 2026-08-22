"""DRF serializers for the journal system."""

from rest_framework import serializers

from world.character_sheets.types import PosthumousJournalDisposition
from world.journals.constants import PosthumousOverride, ResponseType
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
    tags = serializers.SerializerMethodField()
    response_count = serializers.IntegerField(read_only=True, default=0)
    # Posthumous provenance (#3287) — "from the journals of <author_name>, revealed after
    # death" is rendered client-side from author_name + is_posthumous; no server-authored
    # copy string here (deslop: no AI-voice flourish baked into the API).
    is_posthumous = serializers.SerializerMethodField()

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
            "posthumous_override",
            "revealed_at",
            "is_posthumous",
        ]
        read_only_fields = fields

    def get_tags(self, obj: JournalEntry) -> list[dict]:
        """Get tags using cached property."""
        return JournalTagSerializer(obj.cached_tags, many=True).data

    def get_is_posthumous(self, obj: JournalEntry) -> bool:
        """True once this entry has surfaced through an estate settlement."""
        return obj.revealed_at is not None


class JournalEntryDetailSerializer(serializers.ModelSerializer):
    """Full serializer for reading a single journal entry."""

    author_name = serializers.CharField(source="author.character.db_key", read_only=True)
    tags = serializers.SerializerMethodField()
    responses = serializers.SerializerMethodField()
    is_posthumous = serializers.SerializerMethodField()

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
            "posthumous_override",
            "revealed_at",
            "is_posthumous",
        ]
        read_only_fields = fields

    def get_tags(self, obj: JournalEntry) -> list[dict]:
        """Get tags using cached property."""
        return JournalTagSerializer(obj.cached_tags, many=True).data

    def get_responses(self, obj: JournalEntry) -> list[dict]:
        """Return lightweight list of responses."""
        responses = sorted(obj.cached_responses, key=lambda r: r.created_at, reverse=True)
        return JournalEntryListSerializer(responses, many=True).data

    def get_is_posthumous(self, obj: JournalEntry) -> bool:
        """True once this entry has surfaced through an estate settlement."""
        return obj.revealed_at is not None


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
    # Per-entry posthumous override (#3287); INHERIT falls through to the author's sheet
    # default. Optional — the composer only shows this when the author wants to override.
    posthumous_override = serializers.ChoiceField(
        choices=PosthumousOverride.choices,
        default=PosthumousOverride.INHERIT,
        required=False,
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
    # Per-entry posthumous override (#3287) — settable on its own, without title/body.
    posthumous_override = serializers.ChoiceField(
        choices=PosthumousOverride.choices, required=False
    )

    def validate(self, attrs: dict) -> dict:
        has_content = attrs.get("title") or attrs.get("body")
        has_override = "posthumous_override" in attrs
        if not has_content and not has_override:
            msg = "At least one of title, body, or posthumous_override is required."
            raise serializers.ValidationError(msg)
        return attrs


class JournalDispositionSerializer(serializers.Serializer):
    """Serializer for setting the caller's sheet-level posthumous journal disposition."""

    disposition = serializers.ChoiceField(choices=PosthumousJournalDisposition.choices)
