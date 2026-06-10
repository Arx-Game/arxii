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

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from actions.constants import ActionBackend, ActionCategory
from actions.errors import ActionDispatchError
from actions.result_extraction import extract_dispatch_message_data
from actions.types import ActionRef, DispatchResult, PlayerAction


class CheckTypeMinimalSerializer(serializers.Serializer):
    """Minimal read-only representation of a CheckType model instance."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class ActionTemplateMinimalSerializer(serializers.Serializer):
    """Minimal read-only representation of an ActionTemplate model instance."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    default_delivery = serializers.CharField(read_only=True)


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
    clash_id = serializers.IntegerField(allow_null=True, required=False)
    clash_action_slot = serializers.CharField(allow_null=True, required=False)


class SoulfrayWarningSerializer(serializers.Serializer):
    """Minimal read-only representation of a SoulfrayWarning dataclass."""

    stage_name = serializers.CharField(read_only=True)
    stage_description = serializers.CharField(read_only=True)
    has_death_risk = serializers.BooleanField(read_only=True)


class AvailableEnhancementSerializer(serializers.Serializer):
    """Read-only serializer for AvailableEnhancement (technique enhancement option)."""

    technique_id = serializers.IntegerField(source="technique.id", read_only=True)
    technique_name = serializers.CharField(source="technique.name", read_only=True)
    effective_cost = serializers.IntegerField(read_only=True)
    soulfray_warning = SoulfrayWarningSerializer(allow_null=True, read_only=True)


class TargetFiltersSerializer(serializers.Serializer):
    """Read-only serializer for TargetFilters — boolean filter flags."""

    in_same_scene = serializers.BooleanField(read_only=True)
    in_same_zone = serializers.BooleanField(read_only=True)
    exclude_self = serializers.BooleanField(read_only=True)
    must_be_conscious = serializers.BooleanField(read_only=True)


class TargetSpecSerializer(serializers.Serializer):
    """Read-only serializer for TargetSpec — entity kind + cardinality + filters."""

    kind = serializers.CharField(read_only=True)
    cardinality = serializers.CharField(read_only=True)
    filters = TargetFiltersSerializer(read_only=True)


class StrainAvailabilitySerializer(serializers.Serializer):
    """Read-only serializer for StrainAvailability — per-character strain cap snapshot."""

    cap = serializers.IntegerField(read_only=True)
    default = serializers.IntegerField(read_only=True)


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
    target_spec = TargetSpecSerializer(read_only=True, allow_null=True)
    enhancements = AvailableEnhancementSerializer(many=True, read_only=True)
    strain = StrainAvailabilitySerializer(read_only=True, allow_null=True)
    action_category = serializers.ChoiceField(
        choices=ActionCategory.choices, read_only=True, allow_null=True
    )

    def get_difficulty(self, obj: PlayerAction) -> str | None:
        """Return the difficulty enum value string, or None."""
        if obj.difficulty is None:
            return None
        return obj.difficulty.value

    @extend_schema_field(CheckTypeMinimalSerializer)
    def get_check_type(self, obj: PlayerAction) -> dict[str, object] | None:
        """Return minimal check_type representation (id + name), or None for clash contributions."""
        if obj.check_type is None:
            return None
        return CheckTypeMinimalSerializer(obj.check_type).data

    @extend_schema_field(ActionTemplateMinimalSerializer)
    def get_action_template(self, obj: PlayerAction) -> dict[str, object] | None:
        """Return minimal action_template representation, or None."""
        if obj.action_template is None:
            return None
        return ActionTemplateMinimalSerializer(obj.action_template).data


# ---------------------------------------------------------------------------
# Dispatch serializers
# ---------------------------------------------------------------------------


class _DispatchRefSerializer(serializers.Serializer):
    """Input-side ref serializer for DispatchActionSerializer.

    Plain Serializer (not DataclassSerializer) — same drf_spectacular reason as
    ActionRefSerializer above. All fields writable (no read_only) so DRF accepts
    them from request.data.
    """

    backend = serializers.CharField()
    challenge_instance_id = serializers.IntegerField(allow_null=True, required=False, default=None)
    approach_id = serializers.IntegerField(allow_null=True, required=False, default=None)
    technique_id = serializers.IntegerField(allow_null=True, required=False, default=None)
    registry_key = serializers.CharField(allow_null=True, required=False, default=None)
    clash_id = serializers.IntegerField(allow_null=True, required=False, default=None)
    clash_action_slot = serializers.CharField(allow_null=True, required=False, default=None)


class DispatchActionSerializer(serializers.Serializer):
    """Input serializer for POST dispatch endpoint.

    Accepts ``{"ref": {...}, "kwargs": {...}}`` and constructs a validated
    ``ActionRef`` instance.  ``ActionRef.__post_init__`` enforces backend↔required-id
    constraints (raises ``ValueError``); we catch that and re-raise as a
    ``ValidationError`` carrying the safe ``ActionDispatchError`` user_message.

    Validation lives ENTIRELY here — the view calls ``is_valid(raise_exception=True)``
    and reads ``validated_data["ref"]`` and ``validated_data["kwargs"]``.
    """

    ref = _DispatchRefSerializer()
    kwargs = serializers.DictField(required=False, default=dict)

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Construct ActionRef from validated primitive fields; catch ValueError → 400."""
        ref_data: dict[str, Any] = data["ref"]
        try:
            backend_value = ref_data["backend"]
            backend = ActionBackend(backend_value)
        except (ValueError, KeyError):
            raise serializers.ValidationError(
                {
                    "ref": {
                        "backend": ActionDispatchError(
                            ActionDispatchError.UNKNOWN_ACTION_REF
                        ).user_message
                    }
                }
            ) from None

        try:
            action_ref = ActionRef(
                backend=backend,
                challenge_instance_id=ref_data.get("challenge_instance_id"),
                approach_id=ref_data.get("approach_id"),
                technique_id=ref_data.get("technique_id"),
                registry_key=ref_data.get("registry_key"),
                clash_id=ref_data.get("clash_id"),
                clash_action_slot=ref_data.get("clash_action_slot"),
            )
        except ValueError:
            raise serializers.ValidationError(
                {"ref": ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF).user_message}
            ) from None

        return {"ref": action_ref, "kwargs": data.get("kwargs") or {}}


class DispatchResultSerializer(serializers.Serializer):
    """Output serializer for POST dispatch endpoint.

    Produces a clean minimal shape: ``{backend, deferred, message, data}``.
    ``detail`` (``ChallengeResolutionResult | ActionResult | None``) is NOT
    deep-serialized to avoid leaking internal model structure.  Instead:
    - ``message`` carries a short human string extracted from ``detail``
      (``detail.challenge_name`` for challenge, ``detail.message`` for action result).
    - ``data`` is a nullable minimal jsonable dict with just a few identifying fields
      (challenge_instance_id, resolution_type for challenge; action-specific keys for others).
    - When deferred, message is a static "Action declared for round resolution." string.

    All new serializers here are plain ``Serializer`` (not DataclassSerializer) —
    no drf_spectacular ``get_type_hints()`` landmine.
    """

    backend = serializers.CharField(read_only=True)
    deferred = serializers.BooleanField(read_only=True)
    message = serializers.CharField(read_only=True, allow_null=True)
    data = serializers.DictField(read_only=True, allow_null=True)

    def to_representation(self, instance: DispatchResult) -> dict[str, Any]:
        """Extract minimal wire representation from a DispatchResult dataclass."""
        backend_value = instance.backend.value

        if instance.deferred:
            return {
                "backend": backend_value,
                "deferred": True,
                "message": "Action declared for round resolution.",
                "data": None,
            }

        message, data = extract_dispatch_message_data(instance.detail)

        return {
            "backend": backend_value,
            "deferred": False,
            "message": message,
            "data": data,
        }
