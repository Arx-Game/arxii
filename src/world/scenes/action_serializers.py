"""Serializers for scene action requests."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.combat.cast_seed import encounter_requiring_risk_acknowledgement
from world.fatigue.constants import EffortLevel
from world.magic.services.hostility import is_technique_hostile
from world.scenes.action_constants import (
    ActionDelivery,
    ActionRequestStatus,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.action_models import SceneActionRequest, SceneActionTarget


def _cap_fury_by_provocation(attrs: dict) -> dict:
    """Reject a fury_commitment that exceeds the initiator's provocation cap,
    or reject if the caster already has the Berserk condition.

    Mirrors _cap_strain_by_anima for the fury lever.
    """
    from world.magic.models import FuryTier  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    fury_commitment_id = attrs.get("fury_commitment_id")
    if not fury_commitment_id:
        return attrs

    # Fury is a technique-cast-only lever: reject if no technique is declared.
    # (SceneActionRequestCreateSerializer exposes technique_id; TechniqueCastCreateSerializer
    # always has technique_id — so the guard is the same for both callers.)
    if not attrs.get("technique_id"):
        raise serializers.ValidationError(
            {"fury_commitment_id": "Fury can only be declared on technique-enhanced actions."}
        )

    fury_anchor_id = attrs.get("fury_anchor_id")
    if not fury_anchor_id:
        raise serializers.ValidationError(
            {"fury_anchor_id": "fury_anchor is required when fury_commitment is declared."}
        )

    try:
        tier = FuryTier.objects.get(pk=fury_commitment_id)
    except FuryTier.DoesNotExist:
        raise serializers.ValidationError({"fury_commitment_id": "Unknown FuryTier."}) from None

    initiator_persona_id = attrs["initiator_persona"]
    try:
        persona = Persona.objects.select_related("character_sheet__character").get(
            pk=initiator_persona_id
        )
    except Persona.DoesNotExist:
        raise serializers.ValidationError(
            {"fury_commitment_id": "Initiator persona not found."}
        ) from None

    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    try:
        anchor_sheet = CharacterSheet.objects.get(pk=fury_anchor_id)
    except CharacterSheet.DoesNotExist:
        raise serializers.ValidationError(
            {"fury_anchor_id": "Anchor character sheet not found."}
        ) from None

    character = persona.character_sheet.character

    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import has_condition  # noqa: PLC0415

    try:
        berserk_template = ConditionTemplate.get_by_name("Berserk")
        if has_condition(character, berserk_template):
            raise serializers.ValidationError(
                {"fury_commitment_id": "Cannot declare fury while already Berserk."}
            )
    except ConditionTemplate.DoesNotExist:
        pass

    from world.magic.services.fury import provocation_cap  # noqa: PLC0415

    cap = provocation_cap(character, anchor_sheet)
    if cap < tier.depth:
        raise serializers.ValidationError(
            {
                "fury_commitment_id": (
                    f"Fury tier depth ({tier.depth}) exceeds provocation cap ({cap})."
                )
            }
        )

    return attrs


def _cap_strain_by_anima(attrs: dict) -> dict:
    """Reject a strain_commitment that exceeds the initiator's available anima.

    Shared by the create + cast serializers. Looks up the
    Persona → CharacterSheet → character → CharacterAnima chain; a missing anima
    row means cap 0 (any non-zero strain rejects). Done in the serializer (not
    the view) per the validation-in-serializer rule.
    """
    from world.magic.models import CharacterAnima  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    strain = attrs.get("strain_commitment", 0) or 0
    if strain <= 0:
        return attrs

    initiator_persona_id = attrs["initiator_persona"]
    try:
        persona = Persona.objects.select_related("character_sheet__character").get(
            pk=initiator_persona_id
        )
    except Persona.DoesNotExist:
        raise serializers.ValidationError(
            {"strain_commitment": "Initiator persona not found."}
        ) from None

    character = persona.character_sheet.character
    try:
        cap = CharacterAnima.objects.get(character=character).current
    except CharacterAnima.DoesNotExist:
        cap = 0

    if strain > cap:
        raise serializers.ValidationError(
            {"strain_commitment": f"Strain commitment ({strain}) exceeds available anima ({cap})."}
        )

    return attrs


class CastPullRequestSerializer(serializers.Serializer):
    """Nested pull declaration on the cast endpoint (#854)."""

    resonance_id = serializers.IntegerField()
    tier = serializers.IntegerField(min_value=1, max_value=3)
    thread_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        max_length=20,
    )


def _validate_cast_pull(attrs: dict) -> dict:
    """Resolve + validate a declared pull against the initiator's sheet.

    Attaches resolved instances to attrs["pull"]["resonance"|"threads"] so the
    view can build a CastPullDeclaration without re-querying. Affordability and
    anchor-involvement stay with spend_resonance_for_pull at charge time.

    Core ID→instance resolution is delegated to
    ``world.combat.pull_helpers.build_cast_pull_declaration`` (the single resolver)
    so there is no duplicate logic here.  The ``ValidationError`` mapping lives here
    at the serializer boundary (per the anti-reinvention rule: MagicError inside the
    helper; ValidationError only at the DRF surface).
    """
    from world.combat.pull_helpers import build_cast_pull_declaration  # noqa: PLC0415
    from world.magic.exceptions import InvalidImbueAmount  # noqa: PLC0415
    from world.magic.models import Technique  # noqa: PLC0415
    from world.magic.services.hostility import is_technique_hostile  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    pull = attrs["pull"]
    try:
        technique = Technique.objects.select_related("effect_type").get(pk=attrs["technique_id"])
    except Technique.DoesNotExist:
        raise serializers.ValidationError({"technique_id": "Unknown technique."}) from None
    if is_technique_hostile(technique):
        msg = "Pulls cannot be declared on hostile casts — combat owns that flow."
        raise serializers.ValidationError({"pull": msg})

    try:
        persona = Persona.objects.get(pk=attrs["initiator_persona"])
    except Persona.DoesNotExist:
        raise serializers.ValidationError({"initiator_persona": "Unknown persona."}) from None

    try:
        declaration = build_cast_pull_declaration(
            persona.character_sheet_id,
            resonance_id=pull["resonance_id"],
            tier=pull["tier"],
            thread_ids=pull["thread_ids"],
        )
    except InvalidImbueAmount as exc:
        raise serializers.ValidationError({"pull": exc.user_message}) from exc

    pull["resonance"] = declaration.resonance
    pull["threads"] = list(declaration.threads)
    return attrs


class TechniqueCastCreateSerializer(serializers.Serializer):
    """Validate input for the standalone technique cast endpoint."""

    scene = serializers.IntegerField()
    initiator_persona = serializers.IntegerField()
    technique_id = serializers.IntegerField()
    target_persona = serializers.IntegerField(required=False, allow_null=True)
    # FILTERED_GROUP casts supply an explicit subset of target persona IDs.
    # The intersection with the technique's eligible scene-set is computed server-side
    # by resolve_targets. Omit for SELF / SINGLE / AREA techniques.
    target_persona_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True,
        allow_empty=False,
    )
    strain_commitment = serializers.IntegerField(min_value=0, required=False, default=0)
    fury_commitment_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    fury_anchor_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    pull = CastPullRequestSerializer(required=False, allow_null=True)
    use_base_form = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict) -> dict:
        """Cap strain by anima; cap fury by provocation; validate pull (#854)."""
        attrs = _cap_strain_by_anima(attrs)
        attrs = _cap_fury_by_provocation(attrs)
        if attrs.get("pull"):
            attrs = _validate_cast_pull(attrs)
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
    target_type = serializers.CharField()
    reach = serializers.CharField()
    target_spec = serializers.SerializerMethodField()

    def get_hostile(self, obj: object) -> bool:
        from world.magic.models.techniques import Technique  # noqa: PLC0415
        from world.magic.services.hostility import is_technique_hostile  # noqa: PLC0415

        if isinstance(obj, Technique):
            return is_technique_hostile(obj)
        # obj may be a CharacterTechnique — fall back to its technique.
        technique = getattr(obj, "technique", None)  # noqa: GETATTR_LITERAL
        if isinstance(technique, Technique):
            return is_technique_hostile(technique)
        return False

    def get_target_spec(self, obj: object) -> dict | None:
        """Derive and serialize the TargetSpec for this technique.

        Returns None for SELF-targeting techniques (no picker needed). For other
        cardinalities, returns the same shape as actions.serializers.TargetSpecSerializer.
        """
        from actions.player_interface import _target_spec_for_technique_action  # noqa: PLC0415
        from world.magic.models.techniques import Technique  # noqa: PLC0415

        if isinstance(obj, Technique):
            technique_id = obj.pk
        else:
            technique = getattr(obj, "technique", None)  # noqa: GETATTR_LITERAL
            if not isinstance(technique, Technique):
                return None
            technique_id = technique.pk

        spec = _target_spec_for_technique_action(technique_id)
        if spec is None:
            return None
        return {
            "kind": spec.kind,
            "cardinality": spec.cardinality,
            "filters": {
                "in_same_scene": spec.filters.in_same_scene,
                "exclude_self": spec.filters.exclude_self,
                "must_be_conscious": spec.filters.must_be_conscious,
            },
        }


class SceneActionRequestSerializer(serializers.ModelSerializer):
    initiator_name = serializers.CharField(source="initiator_persona.name", read_only=True)
    target_name = serializers.CharField(source="target_persona.name", read_only=True)
    technique_name = serializers.SerializerMethodField()
    combat_risk_level = serializers.SerializerMethodField()

    def get_technique_name(self, obj: SceneActionRequest) -> str | None:
        """Human label for the enhancing technique (#892 — ConsentPrompt display)."""
        return obj.technique.name if obj.technique_id else None

    def get_combat_risk_level(self, obj: SceneActionRequest) -> str | None:
        """Risk level of the encounter a PENDING hostile cast would pull the target into (#777)."""
        if obj.status != ActionRequestStatus.PENDING or not obj.is_standalone_cast:
            return None
        if obj.target_persona is None or not is_technique_hostile(obj.technique):
            return None
        encounter = encounter_requiring_risk_acknowledgement(
            obj.scene, obj.target_persona.character_sheet
        )
        return encounter.risk_level if encounter is not None else None

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
            "technique_name",
            "delivery",
            "status",
            "difficulty_choice",
            "resolved_difficulty",
            "result_interaction",
            "action_interaction",
            "strain_commitment",
            "combat_risk_level",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "combat_risk_level",
            "resolved_difficulty",
            "result_interaction",
            "action_interaction",
            "created_at",
            "resolved_at",
        ]


class SceneActionRequestCreateSerializer(serializers.Serializer):
    scene = serializers.IntegerField()
    initiator_persona = serializers.IntegerField()
    target_persona = serializers.IntegerField(required=False)
    target_persona_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=False
    )
    action_key = serializers.CharField(max_length=100)
    effort_level = serializers.ChoiceField(
        choices=EffortLevel.choices, required=False, default="medium"
    )
    technique_id = serializers.IntegerField(required=False, allow_null=True)
    strain_commitment = serializers.IntegerField(min_value=0, required=False, default=0)
    fury_commitment_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    fury_anchor_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    delivery = serializers.ChoiceField(
        choices=ActionDelivery.choices, required=False, allow_blank=True, default=""
    )
    delivery_receiver_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True, default=list
    )
    # Treatment consent flow (#1486): only meaningful when action_key ==
    # "treat_condition". Cardinality/relationship validation lives in the view
    # (it needs DB lookups + the candidate query); do NOT add these to validate().
    treatment_id = serializers.IntegerField(required=False, allow_null=True)
    target_condition_instance_id = serializers.IntegerField(required=False, allow_null=True)
    target_pending_alteration_id = serializers.IntegerField(required=False, allow_null=True)
    bond_thread_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        """Normalize target fields into ``target_ids``; cap strain and fury.

        ``target_persona_ids`` is authoritative when present (deduped, order
        preserved).  When only ``target_persona`` is given it is wrapped into a
        single-element list.  When both are sent, ``target_persona`` must equal
        ``target_persona_ids[0]``.  The normalised list is written to
        ``attrs["target_ids"]``; cardinality enforcement is the view's job.
        Strain is capped by anima and fury by the provocation cap.
        """
        ids = attrs.get("target_persona_ids")
        primary = attrs.get("target_persona")
        if ids:
            deduped = list(dict.fromkeys(ids))  # preserve order, drop duplicates
            if primary is not None and primary != deduped[0]:
                raise serializers.ValidationError(
                    {"target_persona": "Must equal target_persona_ids[0] when both are sent."}
                )
            attrs["target_ids"] = deduped
        elif primary is not None:
            attrs["target_ids"] = [primary]
        else:
            attrs["target_ids"] = []
        attrs = _cap_strain_by_anima(attrs)
        return _cap_fury_by_provocation(attrs)


class ConsentResponseSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=ConsentDecision.choices)
    target_persona_id = serializers.IntegerField(required=False)
    difficulty = serializers.ChoiceField(choices=DifficultyChoice.choices, required=False)
    resist_effort = serializers.ChoiceField(
        choices=EffortLevel.choices, required=False, allow_blank=True, default=""
    )


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

    @extend_schema_field(PowerLedgerSerializer)
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


class SceneActionTargetSerializer(serializers.ModelSerializer):
    """Flat read payload for a pending additional-target consent row (#1177)."""

    action_target_id = serializers.IntegerField(source="id", read_only=True)
    action_request_id = serializers.IntegerField(read_only=True)
    target_persona_id = serializers.IntegerField(read_only=True)
    initiator_persona = serializers.IntegerField(
        source="action_request.initiator_persona_id", read_only=True
    )
    initiator_name = serializers.CharField(
        source="action_request.initiator_persona.name", read_only=True
    )
    scene = serializers.IntegerField(source="action_request.scene_id", read_only=True)
    action_key = serializers.CharField(source="action_request.action_key", read_only=True)
    action_template = serializers.IntegerField(
        source="action_request.action_template_id", read_only=True, allow_null=True
    )
    technique = serializers.IntegerField(
        source="action_request.technique_id", read_only=True, allow_null=True
    )
    technique_name = serializers.SerializerMethodField()
    combat_risk_level = serializers.SerializerMethodField()
    pose_text = serializers.CharField(source="action_request.pose_text", read_only=True)
    strain_commitment = serializers.IntegerField(
        source="action_request.strain_commitment", read_only=True
    )
    created_at = serializers.DateTimeField(source="action_request.created_at", read_only=True)

    def get_technique_name(self, obj: SceneActionTarget) -> str | None:
        """Human label for the enhancing technique (mirrors the request serializer)."""
        technique = obj.action_request.technique
        return technique.name if technique is not None else None

    def get_combat_risk_level(self, obj: SceneActionTarget) -> str | None:
        """Risk level of the encounter this additional target would be pulled into (#1259).

        Mirrors SceneActionRequestSerializer.get_combat_risk_level, re-keyed on the
        row's own target_persona so each additional target of a hostile AOE cast gets
        its own informed-consent warning.
        """
        request = obj.action_request
        if obj.status != ActionRequestStatus.PENDING or not request.is_standalone_cast:
            return None
        if request.technique is None or not is_technique_hostile(request.technique):
            return None
        encounter = encounter_requiring_risk_acknowledgement(
            request.scene, obj.target_persona.character_sheet
        )
        return encounter.risk_level if encounter is not None else None

    class Meta:
        model = SceneActionTarget
        fields = [
            "action_target_id",
            "action_request_id",
            "target_persona_id",
            "status",
            "initiator_persona",
            "initiator_name",
            "scene",
            "action_key",
            "action_template",
            "technique",
            "technique_name",
            "combat_risk_level",
            "pose_text",
            "strain_commitment",
            "created_at",
        ]
        read_only_fields = [
            "action_target_id",
            "action_request_id",
            "target_persona_id",
            "status",
            "initiator_persona",
            "initiator_name",
            "scene",
            "action_key",
            "action_template",
            "technique",
            "technique_name",
            "combat_risk_level",
            "pose_text",
            "strain_commitment",
            "created_at",
        ]
