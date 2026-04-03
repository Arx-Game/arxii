"""Serializers for scene action requests."""

from __future__ import annotations

from rest_framework import serializers

from world.scenes.action_constants import ConsentDecision
from world.scenes.action_models import SceneActionRequest


class SceneActionRequestSerializer(serializers.ModelSerializer):
    initiator_name = serializers.CharField(source="initiator_persona.name", read_only=True)
    target_name = serializers.CharField(source="target_persona.name", read_only=True)

    class Meta:
        model = SceneActionRequest
        fields = [
            "id",
            "scene",
            "initiator_persona",
            "initiator_name",
            "target_persona",
            "target_name",
            "action_key",
            "action_template",
            "technique",
            "status",
            "difficulty_choice",
            "resolved_difficulty",
            "result_interaction",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "resolved_difficulty",
            "result_interaction",
            "created_at",
            "resolved_at",
        ]


class SceneActionRequestCreateSerializer(serializers.Serializer):
    scene = serializers.IntegerField()
    initiator_persona = serializers.IntegerField()
    target_persona = serializers.IntegerField()
    action_key = serializers.CharField(max_length=100)
    difficulty_choice = serializers.CharField(max_length=20, required=False)
    technique_id = serializers.IntegerField(required=False, allow_null=True)


class ConsentResponseSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=ConsentDecision.choices)


class StepResultSerializer(serializers.Serializer):
    step_label = serializers.CharField()
    check_outcome = serializers.SerializerMethodField()
    consequence_id = serializers.IntegerField(allow_null=True)

    def get_check_outcome(self, obj: object) -> str | None:
        from actions.types import StepResult  # noqa: PLC0415

        if not isinstance(obj, StepResult):
            return None
        return obj.check_result.outcome_name


class ActionResolutionSerializer(serializers.Serializer):
    current_phase = serializers.CharField()
    main_result = StepResultSerializer(allow_null=True)
    gate_results = StepResultSerializer(many=True)


class TechniqueResultSerializer(serializers.Serializer):
    confirmed = serializers.BooleanField()
    anima_spent = serializers.SerializerMethodField()
    soulfray_stage = serializers.SerializerMethodField()
    mishap_label = serializers.SerializerMethodField()

    def get_anima_spent(self, obj: object) -> int | None:
        from world.magic.types import TechniqueUseResult  # noqa: PLC0415

        if not isinstance(obj, TechniqueUseResult):
            return None
        return obj.anima_cost.effective_cost

    def get_soulfray_stage(self, obj: object) -> str | None:
        from world.magic.types import TechniqueUseResult  # noqa: PLC0415

        if not isinstance(obj, TechniqueUseResult):
            return None
        if obj.soulfray_result and obj.soulfray_result.stage_name:
            return obj.soulfray_result.stage_name
        return None

    def get_mishap_label(self, obj: object) -> str | None:
        from world.magic.types import TechniqueUseResult  # noqa: PLC0415

        if not isinstance(obj, TechniqueUseResult):
            return None
        if obj.mishap:
            return obj.mishap.consequence_label
        return None


class EnhancedSceneActionResultSerializer(serializers.Serializer):
    action_key = serializers.CharField()
    action_resolution = ActionResolutionSerializer()
    technique_result = TechniqueResultSerializer(allow_null=True)


class SoulfrayWarningSerializer(serializers.Serializer):
    stage_name = serializers.CharField()
    stage_description = serializers.CharField()
    has_death_risk = serializers.BooleanField()


class AvailableEnhancementSerializer(serializers.Serializer):
    technique_id = serializers.SerializerMethodField()
    technique_name = serializers.SerializerMethodField()
    variant_name = serializers.SerializerMethodField()
    effective_cost = serializers.IntegerField()
    soulfray_warning = SoulfrayWarningSerializer(allow_null=True)

    def get_technique_id(self, obj: object) -> int | None:
        from world.scenes.action_availability import AvailableEnhancement  # noqa: PLC0415

        if not isinstance(obj, AvailableEnhancement):
            return None
        return obj.technique.pk

    def get_technique_name(self, obj: object) -> str | None:
        from world.scenes.action_availability import AvailableEnhancement  # noqa: PLC0415

        if not isinstance(obj, AvailableEnhancement):
            return None
        return obj.technique.name

    def get_variant_name(self, obj: object) -> str | None:
        from world.scenes.action_availability import AvailableEnhancement  # noqa: PLC0415

        if not isinstance(obj, AvailableEnhancement):
            return None
        return obj.enhancement.variant_name


class AvailableSceneActionSerializer(serializers.Serializer):
    action_key = serializers.CharField()
    action_template_name = serializers.SerializerMethodField()
    icon = serializers.SerializerMethodField()
    enhancements = AvailableEnhancementSerializer(many=True)

    def get_action_template_name(self, obj: object) -> str | None:
        from world.scenes.action_availability import AvailableSceneAction  # noqa: PLC0415

        if not isinstance(obj, AvailableSceneAction):
            return None
        return obj.action_template.name

    def get_icon(self, obj: object) -> str | None:
        from world.scenes.action_availability import AvailableSceneAction  # noqa: PLC0415

        if not isinstance(obj, AvailableSceneAction):
            return None
        return obj.action_template.icon
