"""Serializers for scene action requests."""

from __future__ import annotations

from rest_framework import serializers

from world.scenes.action_constants import ConsentDecision
from world.scenes.action_models import SceneActionRequest


class TechniqueCastCreateSerializer(serializers.Serializer):
    """Validate input for the standalone technique cast endpoint."""

    scene = serializers.IntegerField()
    initiator_persona = serializers.IntegerField()
    technique_id = serializers.IntegerField()
    target_persona = serializers.IntegerField(required=False, allow_null=True)
    strain_commitment = serializers.IntegerField(min_value=0, required=False, default=0)

    def validate(self, attrs: dict) -> dict:
        """Cap strain_commitment by the initiator's available anima (same rule as create)."""
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


class CastableTechniqueSerializer(serializers.Serializer):
    """Serializes a Technique for the castable-techniques list endpoint."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    anima_cost = serializers.IntegerField()
    tier = serializers.IntegerField()
    intensity = serializers.IntegerField()
    control = serializers.IntegerField()
    hostile = serializers.SerializerMethodField()

    def get_hostile(self, obj: object) -> bool:
        from world.magic.models.techniques import Technique  # noqa: PLC0415
        from world.magic.services.hostility import is_technique_hostile  # noqa: PLC0415

        if isinstance(obj, Technique):
            return is_technique_hostile(obj)
        # obj may be a CharacterTechnique — fall back to its technique.
        technique = getattr(obj, "technique", None)
        if isinstance(technique, Technique):
            return is_technique_hostile(technique)
        return False


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


class PowerLedgerEntrySerializer(serializers.Serializer):
    """Serializes a single PowerLedgerEntry for the API payload."""

    stage = serializers.CharField()
    source_label = serializers.CharField()
    op = serializers.CharField()
    amount = serializers.IntegerField()
    running_total = serializers.IntegerField()


class PowerLedgerSerializer(serializers.Serializer):
    """Serializes a PowerLedger (entries + total) for the cast result payload."""

    entries = PowerLedgerEntrySerializer(many=True)
    total = serializers.IntegerField()


class EnhancedSceneActionResultSerializer(serializers.Serializer):
    action_key = serializers.CharField()
    action_resolution = ActionResolutionSerializer()
    technique_result = TechniqueResultSerializer(allow_null=True)
    anima_recovery = serializers.SerializerMethodField()
    power_ledger = serializers.SerializerMethodField()

    def get_power_ledger(self, obj: object) -> dict | None:
        """Return the power ledger attached to the result object, if present."""
        from world.scenes.types import EnhancedSceneActionResult  # noqa: PLC0415

        if not isinstance(obj, EnhancedSceneActionResult):
            return None
        ledger = obj.power_ledger
        if ledger is None:
            return None
        return PowerLedgerSerializer(ledger).data

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
        payload = getattr(action_request, "_anima_recovery_payload", None)  # noqa: GETATTR_LITERAL
        return AnimaRecoverySerializer(payload).data if payload is not None else None
