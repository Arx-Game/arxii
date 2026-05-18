"""Serializers for the actions API.

Wire shape for PlayerAction:
{
    "backend": "challenge" | "combat" | "registry",
    "display_name": "Slash with Burning Sword",
    "description": "...",
    "difficulty": "moderate" | null,
    "prerequisite_met": true,
    "prerequisite_reasons": [],
    "check_type": {"id": 1, "name": "Melee"},
    "action_template": {"id": 3, "name": "Basic Strike"} | null,
    "ref": {
        "backend": "challenge",
        "challenge_instance_id": 7,
        "approach_id": 4,
        "technique_id": null,
        "registry_key": null
    }
}
"""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from actions.types import PlayerAction


class CheckTypeMinimalSerializer(serializers.Serializer):
    """Minimal read-only representation of a CheckType model instance."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class ActionTemplateMinimalSerializer(serializers.Serializer):
    """Minimal read-only representation of an ActionTemplate model instance."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class ActionRefSerializer(serializers.Serializer):
    """Serializer for ActionRef frozen dataclass — the round-trippable dispatch reference.

    Uses a plain Serializer (not DataclassSerializer) to avoid drf_spectacular's
    get_type_hints() introspection, which cannot resolve TYPE_CHECKING-only imports
    (CheckType, ActionTemplate, ChallengeResolutionResult) in actions/types.py and
    crashes with NameError during schema generation.
    """

    backend = serializers.CharField(read_only=True)
    challenge_instance_id = serializers.IntegerField(allow_null=True, required=False)
    approach_id = serializers.IntegerField(allow_null=True, required=False)
    technique_id = serializers.IntegerField(allow_null=True, required=False)
    registry_key = serializers.CharField(allow_null=True, required=False)


class PlayerActionSerializer(serializers.Serializer):
    """Read-only serializer for PlayerAction — the homogeneous availability descriptor.

    Does NOT use DataclassSerializer because PlayerAction contains Django model
    instances (check_type, action_template) that DataclassSerializer cannot render.
    Uses explicit field definitions with SerializerMethodField for the model instances.
    """

    backend = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    difficulty = serializers.SerializerMethodField()
    prerequisite_met = serializers.BooleanField(read_only=True)
    prerequisite_reasons = serializers.ListField(child=serializers.CharField(), read_only=True)
    check_type = serializers.SerializerMethodField()
    action_template = serializers.SerializerMethodField()
    ref = ActionRefSerializer(read_only=True)

    def get_difficulty(self, obj: PlayerAction) -> str | None:
        """Return the difficulty enum value string, or None."""
        if obj.difficulty is None:
            return None
        return obj.difficulty.value

    @extend_schema_field(CheckTypeMinimalSerializer)
    def get_check_type(self, obj: PlayerAction) -> dict[str, object]:
        """Return minimal check_type representation (id + name)."""
        return CheckTypeMinimalSerializer(obj.check_type).data

    @extend_schema_field(ActionTemplateMinimalSerializer)
    def get_action_template(self, obj: PlayerAction) -> dict[str, object] | None:
        """Return minimal action_template representation, or None."""
        if obj.action_template is None:
            return None
        return ActionTemplateMinimalSerializer(obj.action_template).data
