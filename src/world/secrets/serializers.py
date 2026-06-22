"""Serializers for the secret tab (#1334) — a viewer's known secrets about a character.

Renders a ``SecretKnowledge`` (a held secret) into the tab shape. The fact (``content``) is
always shown — holding the row *is* the fact layer — but any partial-knowledge layer the viewer
hasn't unlocked (``category``, ``consequences``), and any layer the secret itself leaves
unplaced, renders as **"Unknown"** (a first-class state, not a blank).
"""

from rest_framework import serializers

# Runtime import (not TYPE_CHECKING): drf-spectacular calls get_type_hints() on the method
# fields, which evaluates the ``obj: SecretKnowledge`` annotations — they must resolve at runtime.
from world.secrets.models import SecretKnowledge

UNKNOWN = "Unknown"


class KnownSecretSerializer(serializers.Serializer):
    """One known secret, from the viewer's side, with locked layers shown as "Unknown"."""

    id = serializers.IntegerField(source="secret_id", read_only=True)
    level = serializers.CharField(source="secret.get_level_display", read_only=True)
    content = serializers.CharField(source="secret.content", read_only=True)
    provenance = serializers.CharField(source="secret.get_provenance_display", read_only=True)
    found_at = serializers.DateTimeField(read_only=True)
    subject = serializers.SerializerMethodField()
    second_party = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    consequences = serializers.SerializerMethodField()
    author = serializers.SerializerMethodField()

    def get_subject(self, obj: SecretKnowledge) -> str:
        return obj.secret.subject_sheet.character.db_key

    def get_second_party(self, obj: SecretKnowledge) -> str | None:
        other = obj.secret.second_party_sheet
        return other.character.db_key if other is not None else None

    def get_category(self, obj: SecretKnowledge) -> str:
        secret = obj.secret
        if obj.knows_category and secret.category_id is not None:
            return secret.category.name
        return UNKNOWN

    def get_consequences(self, obj: SecretKnowledge) -> str:
        if obj.knows_consequences and obj.secret.consequences:
            return obj.secret.consequences
        return UNKNOWN

    def get_author(self, obj: SecretKnowledge) -> str:
        persona = obj.secret.author_persona
        return persona.name if persona is not None else "GM/Staff"
