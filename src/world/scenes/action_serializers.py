"""Serializers for scene action requests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.combat.cast_seed import encounter_requiring_risk_acknowledgement
from world.fatigue.constants import EffortLevel
from world.magic.services.hostility import is_technique_hostile
from world.scenes.action_constants import (
    ActionDelivery,
    ActionRequestStatus,
    BoonKind,
    BoonSumTier,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.action_models import SceneActionRequest, SceneActionTarget

if TYPE_CHECKING:
    from world.scenes.models import Scene


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


def _validate_pull_declaration(attrs: dict, *, hostile_check: bool = False) -> dict:
    """Resolve + validate a declared pull against the initiator's sheet.

    Attaches resolved instances to attrs["pull"]["resonance"|"threads"] so the
    view can build a CastPullDeclaration without re-querying. Affordability and
    anchor-involvement stay with spend_resonance_for_pull at charge time.

    Core ID→instance resolution is delegated to
    ``world.combat.pull_helpers.build_cast_pull_declaration`` (the single resolver)
    so there is no duplicate logic here.  The ``ValidationError`` mapping lives here
    at the serializer boundary (per the anti-reinvention rule: MagicError inside the
    helper; ValidationError only at the DRF surface).

    Args:
        attrs: The serializer attrs dict (must contain ``pull`` and
            ``initiator_persona``; ``technique_id`` when ``hostile_check``).
        hostile_check: When True (cast path), reject hostile techniques and
            require ``technique_id``. When False (social path), skip both.

    Raises:
        serializers.ValidationError: On ownership/resonance mismatch, unknown
            technique, hostile technique (cast path only), or unknown persona.
    """
    from world.combat.pull_helpers import build_cast_pull_declaration  # noqa: PLC0415
    from world.magic.exceptions import InvalidImbueAmount  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    pull = attrs["pull"]

    if hostile_check:
        from world.magic.models import Technique  # noqa: PLC0415
        from world.magic.services.hostility import is_technique_hostile  # noqa: PLC0415

        try:
            technique = Technique.objects.select_related("effect_type").get(
                pk=attrs["technique_id"]
            )
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


def _validate_cast_pull(attrs: dict) -> dict:
    """Cast-specific wrapper: validates the pull with the hostile-technique check.

    Delegates to ``_validate_pull_declaration(hostile_check=True)``.
    """
    return _validate_pull_declaration(attrs, hostile_check=True)


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
        from world.magic.models.techniques import CharacterTechnique  # noqa: PLC0415

        if isinstance(obj, CharacterTechnique):
            return is_technique_hostile(obj.technique)
        return False

    def get_target_spec(self, obj: object) -> dict | None:
        """Derive and serialize the TargetSpec for this technique.

        Returns None for SELF-targeting techniques (no picker needed). For other
        cardinalities, returns the same shape as actions.serializers.TargetSpecSerializer.
        """
        from actions.player_interface import _target_spec_for_technique_action  # noqa: PLC0415
        from world.magic.models.techniques import (  # noqa: PLC0415
            CharacterTechnique,
            Technique,
        )

        if isinstance(obj, Technique):
            technique_id = obj.pk
        elif isinstance(obj, CharacterTechnique):
            technique_id = obj.technique_id
        else:
            return None

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


def _stakes_summaries_for_scene(scene: Scene) -> list[dict] | None:
    """Stakes-summary payloads for a scene's staked UNSATISFIED beats (#1770 PR4).

    One stakes-summary dict per staked beat, or None when the scene carries
    none. Uncached — callers memoize per serializer instance.
    """
    from world.combat.beat_wiring import staked_unsatisfied_beats_for_scene  # noqa: PLC0415
    from world.stories.serializers import stakes_summary_for_beat  # noqa: PLC0415

    beats = staked_unsatisfied_beats_for_scene(scene)
    if not beats:
        return None
    return [stakes_summary_for_beat(beat) for beat in beats]


class _CombatStakesCacheMixin:
    """Per-instance memoization for the consent-prompt risk/stakes fields (#1770 PR4).

    With ``many=True`` DRF reuses ONE child serializer instance for every
    row, so these caches make N rows cost one gating-encounter lookup per
    row (shared by combat_risk_level AND combat_stakes) and one
    stakes-discovery + summary pass per scene.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._gating_risk_by_pk: dict[int, str | None] = {}
        self._stakes_by_scene_id: dict[int, list[dict] | None] = {}

    def _compute_gating_risk(self, obj: Any) -> str | None:
        msg = "Subclasses must implement _compute_gating_risk."
        raise NotImplementedError(msg)

    def _gating_risk(self, obj: Any) -> str | None:
        """The row's gating-encounter risk level, computed once per row."""
        if obj.pk not in self._gating_risk_by_pk:
            self._gating_risk_by_pk[obj.pk] = self._compute_gating_risk(obj)
        return self._gating_risk_by_pk[obj.pk]

    def _stakes_for_scene(self, scene: Scene) -> list[dict] | None:
        """The scene's stakes summaries, computed once per scene."""
        if scene.pk not in self._stakes_by_scene_id:
            self._stakes_by_scene_id[scene.pk] = _stakes_summaries_for_scene(scene)
        return self._stakes_by_scene_id[scene.pk]


class SceneActionRequestSerializer(_CombatStakesCacheMixin, serializers.ModelSerializer):
    initiator_name = serializers.CharField(source="initiator_persona.name", read_only=True)
    target_name = serializers.CharField(source="target_persona.name", read_only=True)
    technique_name = serializers.SerializerMethodField()
    combat_risk_level = serializers.SerializerMethodField()
    combat_stakes = serializers.SerializerMethodField()
    boon = serializers.SerializerMethodField()

    def get_technique_name(self, obj: SceneActionRequest) -> str | None:
        """Human label for the enhancing technique (#892 — ConsentPrompt display)."""
        return obj.technique.name if obj.technique_id else None

    def get_boon(self, obj: SceneActionRequest) -> dict | None:
        """The structured ask riding this request (#2540) — what the defender is asked for.

        The specified-up-front payload is what lets a piloted target gauge whether it's
        an easy "just no": kind, the sum tier + frozen coppers for money, the item's
        display name, or the deed text.
        """
        from world.scenes.boon_models import Boon  # noqa: PLC0415

        row = Boon.objects.filter(action_request=obj).first()
        if row is None:
            return None
        return {
            "kind": row.kind,
            "sum_tier": row.sum_tier,
            "amount": row.amount,
            "item_name": str(row.item_instance) if row.item_instance_id else None,
            "deed_text": row.deed_text,
        }

    def _compute_gating_risk(self, obj: SceneActionRequest) -> str | None:
        if obj.status != ActionRequestStatus.PENDING or not obj.is_standalone_cast:
            return None
        if obj.target_persona is None or not is_technique_hostile(obj.technique):
            return None
        encounter = encounter_requiring_risk_acknowledgement(
            obj.scene, obj.target_persona.character_sheet
        )
        return encounter.risk_level if encounter is not None else None

    def get_combat_risk_level(self, obj: SceneActionRequest) -> str | None:
        """Risk level of the encounter a PENDING hostile cast would pull the target into (#777)."""
        return self._gating_risk(obj)

    def get_combat_stakes(self, obj: SceneActionRequest) -> list[dict] | None:
        """Stakes summaries for staked beats behind the gating encounter (#1770 pillar 9).

        Non-None only when the same #777 gate that drives combat_risk_level is
        active AND the scene carries staked, still-open beats — the consent
        prompt is the target's commit moment, so they see what is wagered.
        Same shape as the BeatViewSet stakes-summary payload (one entry per
        staked beat); branch contents are never included.
        """
        if self._gating_risk(obj) is None:
            return None
        return self._stakes_for_scene(obj.scene)

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
            "combat_stakes",
            "boon",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "combat_risk_level",
            "combat_stakes",
            "boon",
            "resolved_difficulty",
            "result_interaction",
            "action_interaction",
            "created_at",
            "resolved_at",
        ]


class BoonSumOptionSerializer(serializers.Serializer):
    """One money-sum option against a specific target (#2540 — 'Fair (200g)')."""

    tier = serializers.ChoiceField(choices=BoonSumTier.choices)
    label = serializers.CharField()
    coppers = serializers.IntegerField()


class BoonOptionsSerializer(serializers.Serializer):
    """Schema shape for the boon-options read (empty list = no money option shown)."""

    sum_tiers = BoonSumOptionSerializer(many=True)


class BoonAskSerializer(serializers.Serializer):
    """The structured-ask payload on a `boon` dispatch (#2540).

    MONEY asks carry a ``sum_tier`` (never a raw amount — the concrete coppers derive
    from the target's purse server-side); item asks name an ``item_instance_id``; DEED
    asks carry the deed text. Eligibility itself is validated by
    ``validate_boon_ask`` inside ``create_action_request`` — this serializer only
    shapes the payload.
    """

    kind = serializers.ChoiceField(choices=BoonKind.choices)
    sum_tier = serializers.ChoiceField(
        choices=BoonSumTier.choices, required=False, allow_blank=True, default=""
    )
    item_instance_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    deed_text = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)


class SceneActionRequestCreateSerializer(serializers.Serializer):
    scene = serializers.IntegerField()
    # Not required at the field level: the entrance-technique branch resolves the
    # actor's own puppet instead of trusting a client-supplied persona id (see
    # SceneActionRequestViewSet._create_technique_entrance). The view still 400s
    # when it's missing on every OTHER action_key, so this is a behavior-preserving
    # relaxation of this one field, not a broadening of the generic path (#2183).
    initiator_persona = serializers.IntegerField(required=False, allow_null=True)
    target_persona = serializers.IntegerField(required=False)
    target_persona_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=False
    )
    action_key = serializers.CharField(max_length=100)
    effort_level = serializers.ChoiceField(
        choices=EffortLevel.choices, required=False, default="medium"
    )
    technique_id = serializers.IntegerField(required=False, allow_null=True)
    # Technique-driven combat entrance (#2183): the freshly-created ENTRY pose
    # Interaction id, so EntranceAction can anchor the entrance to the pose that
    # announced it. Only meaningful when action_key == "entrance" and technique_id
    # is set — see EntranceAction._execute_technique_entrance.
    entry_interaction_id = serializers.IntegerField(required=False, allow_null=True)
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
    # #1919: Optional thread-pull declaration on social actions. Validated via
    # _validate_pull_declaration (social path — no hostile-technique check).
    pull = CastPullRequestSerializer(required=False, allow_null=True)
    # #2540: the structured-ask payload — only meaningful when action_key == "boon".
    # Eligibility (dial 1) is validated by create_action_request before any row exists.
    boon = BoonAskSerializer(required=False, allow_null=True)

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
        attrs = _cap_fury_by_provocation(attrs)
        if attrs.get("pull"):
            attrs = _validate_pull_declaration(attrs, hostile_check=False)
        return attrs


class ConsentResponseSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=ConsentDecision.choices)
    target_persona_id = serializers.IntegerField(required=False)
    difficulty = serializers.ChoiceField(choices=DifficultyChoice.choices, required=False)
    resist_effort = serializers.ChoiceField(
        choices=EffortLevel.choices, required=False, allow_blank=True, default=""
    )
    # On DENY, also add the initiator to this defender's antagonism blacklist for the
    # action's category (#1698). Ignored on ACCEPT / when the action has no category.
    blacklist_actor = serializers.BooleanField(required=False, default=False)


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
    fizzle_note = serializers.CharField(allow_null=True, required=False)
    disposition_message = serializers.CharField(allow_null=True, required=False)

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
        # Suppression justified: transient side-channel stash from the anima resolver.
        payload = getattr(action_request, "_anima_recovery_payload", None)  # noqa: GETATTR_LITERAL
        return AnimaRecoverySerializer(payload).data if payload is not None else None


class SceneActionTargetSerializer(_CombatStakesCacheMixin, serializers.ModelSerializer):
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
    combat_stakes = serializers.SerializerMethodField()
    pose_text = serializers.CharField(source="action_request.pose_text", read_only=True)
    strain_commitment = serializers.IntegerField(
        source="action_request.strain_commitment", read_only=True
    )
    created_at = serializers.DateTimeField(source="action_request.created_at", read_only=True)

    def get_technique_name(self, obj: SceneActionTarget) -> str | None:
        """Human label for the enhancing technique (mirrors the request serializer)."""
        technique = obj.action_request.technique
        return technique.name if technique is not None else None

    def _compute_gating_risk(self, obj: SceneActionTarget) -> str | None:
        request = obj.action_request
        if obj.status != ActionRequestStatus.PENDING or not request.is_standalone_cast:
            return None
        if request.technique is None or not is_technique_hostile(request.technique):
            return None
        encounter = encounter_requiring_risk_acknowledgement(
            request.scene, obj.target_persona.character_sheet
        )
        return encounter.risk_level if encounter is not None else None

    def get_combat_risk_level(self, obj: SceneActionTarget) -> str | None:
        """Risk level of the encounter this additional target would be pulled into (#1259).

        Mirrors SceneActionRequestSerializer.get_combat_risk_level, re-keyed on the
        row's own target_persona so each additional target of a hostile AOE cast gets
        its own informed-consent warning.
        """
        return self._gating_risk(obj)

    def get_combat_stakes(self, obj: SceneActionTarget) -> list[dict] | None:
        """Stakes summaries for this target's gating encounter (#1770 pillar 9).

        Mirrors SceneActionRequestSerializer.get_combat_stakes for each
        additional target of a hostile AOE cast.
        """
        if self._gating_risk(obj) is None:
            return None
        return self._stakes_for_scene(obj.action_request.scene)

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
            "combat_stakes",
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
            "combat_stakes",
            "pose_text",
            "strain_commitment",
            "created_at",
        ]
