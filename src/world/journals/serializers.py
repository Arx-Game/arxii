"""DRF serializers for the journal system."""

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from world.character_sheets.types import PosthumousJournalDisposition, RetortConsent
from world.journals.constants import PosthumousOverride, ResponseType
from world.journals.models import JournalEntry, JournalTag
from world.journals.services import can_retort

# Serializer field names, extracted to satisfy the string-literal lint
# (tools/lint_string_literal.py) at their "<name> in attrs" membership checks below.
_POSTHUMOUS_OVERRIDE_FIELD = "posthumous_override"
_ABOUT_FIELD = "about"
_DISPOSITION_FIELD = "disposition"
_RETORT_CONSENT_FIELD = "retort_consent"


class JournalTagSerializer(serializers.ModelSerializer):
    """Serializer for journal tags."""

    class Meta:
        model = JournalTag
        fields = ["id", "name"]
        read_only_fields = ["id"]


class _ViewerFieldsMixin(serializers.Serializer):
    """Reader-relative fields shared by the list and detail serializers (#3941).

    Inherits from ``serializers.Serializer`` (not a bare mixin) so its
    ``SerializerMethodField`` declarations go through DRF's ``SerializerMetaclass`` and
    land in ITS OWN ``_declared_fields`` — a plain-object mixin's fields never make it
    into a ``ModelSerializer`` subclass's ``_declared_fields`` (only base classes that
    carry that attribute are walked), so ``Meta.fields`` would otherwise try to resolve
    them as real ``JournalEntry`` model fields and fail loudly at request time.

    Each field depends on ``context["viewer_sheet"]`` (the requesting character's
    sheet, or ``None`` for a docked-but-characterless account) rather than a memo on
    the serializer instance (ADR-0260) — the viewer differs per request, so nothing
    here is safe to cache across calls.
    """

    author_persona_id = serializers.SerializerMethodField()
    can_retort = serializers.SerializerMethodField()
    is_own = serializers.SerializerMethodField()

    def get_author_persona_id(self, obj: JournalEntry) -> int | None:
        """The author's primary persona, for the reader's Mute/Block links (#3941)."""
        try:
            return obj.author.primary_persona.pk
        except ObjectDoesNotExist:
            return None

    def get_can_retort(self, obj: JournalEntry) -> bool:
        """ADR-0307 predicate for the requesting viewer; False without a viewer.

        Prefers the ``viewer_can_retort`` annotation (``services.annotate_can_retort``)
        that the list reads carry, so a page of rows costs no extra query. The detail
        read and the nested responses have no annotation to carry -- they are single
        objects, where one EXISTS is the cheapest thing available -- so they fall back
        to ``services.can_retort``, which is where the predicate's meaning lives either
        way.
        """
        try:
            return bool(obj.viewer_can_retort)
        except AttributeError:
            viewer = self.context.get("viewer_sheet")
            return can_retort(viewer_sheet=viewer, author=obj.author)

    def get_is_own(self, obj: JournalEntry) -> bool:
        """Whether the requesting viewer wrote this entry; False without a viewer."""
        viewer = self.context.get("viewer_sheet")
        return viewer is not None and obj.author_id == viewer.pk


class JournalEntryListSerializer(_ViewerFieldsMixin, serializers.ModelSerializer):
    """Lightweight serializer for journal feed/list views."""

    author_name = serializers.CharField(source="author.character.db_key", read_only=True)
    tags = serializers.SerializerMethodField()
    response_count = serializers.IntegerField(read_only=True, default=0)
    # Posthumous provenance (#3287) — "from the journals of <author_name>, revealed after
    # death" is rendered client-side from author_name + is_posthumous; no server-authored
    # copy string here (deslop: no AI-voice flourish baked into the API).
    is_posthumous = serializers.SerializerMethodField()
    # The relationship journal's subject (#3941) — a tag needs the subject's consent,
    # an entry ABOUT someone doesn't, so this is a distinct field, not a tag alias.
    about_name = serializers.CharField(
        source="about.character.db_key", read_only=True, default=None
    )
    ic_timestamp = serializers.DateTimeField(read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "author",
            "author_name",
            "author_persona_id",
            "title",
            "body",
            "is_public",
            "kind",
            "response_type",
            "parent",
            "created_at",
            "edited_at",
            "ic_timestamp",
            "tags",
            "response_count",
            "posthumous_override",
            "revealed_at",
            "is_posthumous",
            "about",
            "about_name",
            "can_retort",
            "is_own",
        ]
        read_only_fields = fields

    def get_tags(self, obj: JournalEntry) -> list[dict]:
        """Get tags using cached property."""
        return JournalTagSerializer(obj.cached_tags, many=True).data

    def get_is_posthumous(self, obj: JournalEntry) -> bool:
        """True once this entry has surfaced through an estate settlement."""
        return obj.revealed_at is not None


class JournalEntryDetailSerializer(_ViewerFieldsMixin, serializers.ModelSerializer):
    """Full serializer for reading a single journal entry."""

    author_name = serializers.CharField(source="author.character.db_key", read_only=True)
    tags = serializers.SerializerMethodField()
    responses = serializers.SerializerMethodField()
    is_posthumous = serializers.SerializerMethodField()
    about_name = serializers.CharField(
        source="about.character.db_key", read_only=True, default=None
    )
    ic_timestamp = serializers.DateTimeField(read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "author",
            "author_name",
            "author_persona_id",
            "title",
            "body",
            "is_public",
            "kind",
            "response_type",
            "parent",
            "created_at",
            "edited_at",
            "ic_timestamp",
            "tags",
            "responses",
            "posthumous_override",
            "revealed_at",
            "is_posthumous",
            "about",
            "about_name",
            "can_retort",
            "is_own",
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
    # The relationship journal's subject (#3941); null means "not about anyone in particular."
    about = serializers.IntegerField(required=False, allow_null=True)


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
    # The relationship journal's subject (#3941) — settable on its own; null clears it.
    about = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        has_content = attrs.get("title") or attrs.get("body")
        has_override = _POSTHUMOUS_OVERRIDE_FIELD in attrs or _ABOUT_FIELD in attrs
        if not has_content and not has_override:
            msg = "At least one of title, body, posthumous_override, or about is required."
            raise serializers.ValidationError(msg)
        return attrs


class JournalSettingsSerializer(serializers.Serializer):
    """Read/write the caller's journal settings: posthumous disposition + retort consent.

    ``GET /entries/disposition/`` returns the full ``JournalSettings`` shape (including the
    read-only weekly-post counters); this serializer only validates the two writable fields
    a ``PATCH`` may carry, at least one of which is required (#3941, ADR-0307).
    """

    disposition = serializers.ChoiceField(
        choices=PosthumousJournalDisposition.choices, required=False
    )
    retort_consent = serializers.ChoiceField(choices=RetortConsent.choices, required=False)

    def validate(self, attrs: dict) -> dict:
        if _DISPOSITION_FIELD not in attrs and _RETORT_CONSENT_FIELD not in attrs:
            msg = "At least one of disposition or retort_consent is required."
            raise serializers.ValidationError(msg)
        return attrs
