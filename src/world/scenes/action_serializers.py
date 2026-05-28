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
            "strain_commitment",
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
    strain_commitment = serializers.IntegerField(min_value=0, required=False, default=0)

    def validate(self, attrs: dict) -> dict:
        """Cap strain_commitment by the initiator's available anima.

        Looks up the Persona → CharacterSheet → character → CharacterAnima chain;
        if the row is missing, treat the cap as 0 (any non-zero strain rejects).
        Done here (serializer), not in the view, per the validation-in-serializer rule.
        """
        from world.magic.models import CharacterAnima  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415

        strain = attrs.get("strain_commitment", 0) or 0
        if strain <= 0:
            return attrs

        initiator_persona_id = attrs["initiator_persona"]
        try:
            persona = Persona.objects.select_related(
                "character_sheet__character",
            ).get(pk=initiator_persona_id)
        except Persona.DoesNotExist:
            raise serializers.ValidationError(
                {"strain_commitment": "Initiator persona not found."}
            ) from None

        character = persona.character_sheet.character
        try:
            anima = CharacterAnima.objects.get(character=character)
            cap = anima.current
        except CharacterAnima.DoesNotExist:
            cap = 0

        if strain > cap:
            raise serializers.ValidationError(
                {
                    "strain_commitment": (
                        f"Strain commitment ({strain}) exceeds available anima ({cap})."
                    )
                }
            )

        return attrs


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


class AnimaRecoverySerializer(serializers.Serializer):
    """Recovery values from an accepted anima_ritual action, visible to initiator only."""

    recovered = serializers.IntegerField()
    soulfray_reduced = serializers.IntegerField()
    new_pool = serializers.IntegerField()


class EnhancedSceneActionResultSerializer(serializers.Serializer):
    action_key = serializers.CharField()
    action_resolution = ActionResolutionSerializer()
    technique_result = TechniqueResultSerializer(allow_null=True)
    anima_recovery = serializers.SerializerMethodField()

    def get_anima_recovery(self, obj: object) -> dict | None:
        """Return anima recovery payload for the initiator of an anima_ritual action.

        Populated only when:
        - action_key is "anima_ritual"
        - the request was accepted (resolver attached payload to action_request)
        - the requesting user is the initiator (disguise: target sees nothing)

        The payload is attached to action_request as a transient attribute by
        ``_resolve_anima_ritual`` to avoid a second DB query.
        """
        from world.scenes.types import EnhancedSceneActionResult  # noqa: PLC0415

        if not isinstance(obj, EnhancedSceneActionResult):
            return None
        if obj.action_key != "anima_ritual":  # noqa: STRING_LITERAL
            return None
        action_request = self.context.get("action_request")
        request = self.context.get("request")
        if action_request is None or request is None:
            return None
        initiator_account = action_request.initiator_persona.character_sheet.character.db_account
        if initiator_account is None or request.user != initiator_account:
            return None
        payload = getattr(action_request, "_anima_recovery_payload", None)  # noqa: GETATTR_LITERAL — transient attr set by resolver
        return AnimaRecoverySerializer(payload).data if payload is not None else None
