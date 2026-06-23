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
    # #1429 — whether the viewer is a wronged party who may register a grievance (annotated by the
    # viewset via an Exists subquery); drives the "Respond" affordance on the tab.
    can_grieve = serializers.BooleanField(read_only=True, default=False)
    subject = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    consequences = serializers.SerializerMethodField()
    author = serializers.SerializerMethodField()

    def get_subject(self, obj: SecretKnowledge) -> str:
        return obj.secret.subject_sheet.character.db_key

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


class GrievanceOptionSerializer(serializers.Serializer):
    """A preset grievance swing offered to a wronged character (#1429)."""

    id = serializers.IntegerField(read_only=True)
    label = serializers.CharField(read_only=True)
    points = serializers.IntegerField(read_only=True)
    track = serializers.CharField(source="track.name", read_only=True)


class SecretGrievanceSerializer(serializers.Serializer):
    """Input for a secret-victim registering a grievance (#1429).

    Exactly one of ``option`` or (``custom_points`` + ``custom_track``) is supplied; the view
    resolves the viewing character and enforces victimhood via the service.
    """

    secret = serializers.IntegerField()
    viewer = serializers.IntegerField(help_text="The active (viewing) character's RosterEntry pk.")
    option = serializers.IntegerField(required=False, allow_null=True)
    custom_points = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    custom_track = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        has_option = attrs.get("option") is not None
        has_custom = (
            attrs.get("custom_points") is not None and attrs.get("custom_track") is not None
        )
        if has_option == has_custom:
            msg = "Provide either an option or both custom_points and custom_track."
            raise serializers.ValidationError(msg)
        return attrs
