"""DRF serializers for the missions authoring API (Phase D).

D1 ships ``MissionTemplateSerializer`` (list + detail browse). Editor
CRUD serializers for nodes / options / routes / candidates / rewards
land in D2; giver-library serializers in D3; predicate-tree in D5.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.missions.constants import MissionStatus
from world.missions.models import (
    MissionCategory,
    MissionGiver,
    MissionInstance,
    MissionNode,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionOptionRouteReward,
    MissionTemplate,
)


def _validate_name_unique_on_update(
    instance: object,
    queryset: object,
    value: str,
    label: str,
) -> str:
    """On UPDATE: reject names already taken by another row of the same model.

    On CREATE (instance is None): no-op. The serializer's create() override
    auto-suffixes collisions via next_available_name, so the CREATE path
    must let the value through unchanged.
    """
    if instance is None:
        return value
    if queryset.exclude(pk=instance.pk).filter(name=value).exists():  # type: ignore[union-attr]
        msg = f"A {label} with this name already exists."
        raise serializers.ValidationError(msg)
    return value


class MissionTemplateSerializer(serializers.ModelSerializer):
    """List + detail serializer for MissionTemplate browse.

    Read-only fields cover the authoring footprint: name, summary,
    epilogue, level band, risk tier, weighting, era association, scope,
    cooldown, reward-group rule, active flag, visibility, categories,
    availability rule.

    The visibility flip is a straight write (#870): there is no
    "publish to nobody" failure mode to guard against — a RESTRICTED
    template whose rule admits no PC simply IS staff-only, a valid
    emergent state. ``availability_rule`` IS validated (well-formedness;
    a malformed tree would crash every later availability check).
    """

    class Meta:
        model = MissionTemplate
        fields = [
            "id",
            "name",
            "summary",
            "epilogue",
            "level_band_min",
            "level_band_max",
            "risk_tier",
            "base_weight",
            "created_in_era",
            "arc_scope",
            "percent_replace",
            "cooldown",
            "reward_group_rule",
            "is_active",
            "visibility",
            "categories",
            "availability_rule",
        ]
        read_only_fields = ["id"]
        # Suppress DRF's auto-generated UniqueValidator on ``name``.
        # The create() override calls next_available_name() to resolve
        # collisions via auto-suffix before the DB write, so a
        # UniqueValidator firing before create() would block that logic.
        extra_kwargs = {"name": {"validators": []}}

    def validate_name(self, value: str) -> str:
        """On UPDATE: reject names already taken by another template.

        On CREATE: ``create()`` calls ``next_available_name`` to auto-suffix
        collisions, so this validator returns the value unchanged. We can't
        use DRF's default ``UniqueValidator`` here because it runs before
        ``create()`` and would block the auto-suffix path. PATCH renames
        are intentionally strict — deliberate user choices deserve explicit
        feedback when they conflict.
        """
        return _validate_name_unique_on_update(
            self.instance, MissionTemplate.objects.all(), value, "mission"
        )

    def validate(self, attrs: dict) -> dict:
        """Run ``MissionTemplate._validate_invariants()`` so cross-field rules surface as DRF 400.

        DRF doesn't call ``Model.clean()`` automatically. Both this method and
        ``MissionTemplate.clean()`` delegate to ``_validate_invariants``, which
        is the single source of truth — adding a new invariant there covers both
        paths automatically (the explicit kwargs list makes a missing field a
        NameError at the call site rather than a silent bypass).
        """
        attrs = super().validate(attrs)

        def field(name: str, default: object) -> object:
            if name in attrs:
                return attrs[name]
            if self.instance is not None:
                return getattr(self.instance, name, default)
            return default

        try:
            MissionTemplate.validate_invariants(
                level_band_min=int(field("level_band_min", 0)),
                level_band_max=int(field("level_band_max", 0)),
                percent_replace=int(field("percent_replace", 0)),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs

    def validate_availability_rule(self, value: dict) -> dict:
        """Reject malformed predicate trees at author time (#870).

        Under visibility=eligibility the rule IS the audience gate, and a
        malformed tree (unknown leaf, missing/mistyped param, bad shape)
        doesn't fail at save — it crashes every later availability check
        that evaluates it. ``validate_predicate_tree`` ports the FE
        builder's checks server-side, plus param type checks against the
        same introspected leaf catalog the builder renders from.
        """
        from world.predicates.validation import validate_predicate_tree  # noqa: PLC0415

        errors = validate_predicate_tree(value)
        if errors:
            raise serializers.ValidationError(errors)
        return value

    def create(self, validated_data: dict) -> MissionTemplate:  # type: ignore[override]
        from django.db import IntegrityError, transaction  # noqa: PLC0415

        from world.missions.services.naming import next_available_name  # noqa: PLC0415

        original_name = validated_data["name"]
        validated_data["name"] = next_available_name(original_name, MissionTemplate.objects.all())
        try:
            # Wrap in a savepoint so that if the INSERT fails with
            # IntegrityError, any enclosing @transaction.atomic caller's
            # transaction is NOT poisoned ("current transaction is aborted").
            with transaction.atomic():
                return super().create(validated_data)  # type: ignore[return-value]
        except IntegrityError:
            # Concurrent create with the same name beat us between the
            # next_available_name SELECT and our INSERT. Recompute the
            # suffix (now seeing the just-committed row) and retry once.
            validated_data["name"] = next_available_name(
                original_name, MissionTemplate.objects.all()
            )
            return super().create(validated_data)  # type: ignore[return-value]


class _ActiveInstanceSerializer(serializers.Serializer):
    """One row in the template-detail footprint's ``active_instances`` list.

    Pure serialization — no model bound. Built by the detail view from
    the MissionInstance queryset; carries the bits the authoring tool
    needs at a glance (instance id, where the run sits, who's holding
    the contract). Not a ModelSerializer because the response shape is
    flattened across MissionInstance + MissionParticipant + ObjectDB.
    """

    instance_id = serializers.IntegerField()
    current_node_key = serializers.CharField(allow_null=True)
    contract_holder = serializers.CharField(allow_null=True)


class MissionTemplateDetailSerializer(MissionTemplateSerializer):
    """Detail response: list fields + §5 footprint.

    Adds:
    - ``lifetime_completions`` — count of MissionInstance rows in
      COMPLETE status for this template.
    - ``active_instances`` — list of currently-ACTIVE runs with their
      current node key + contract holder name.

    The authoring tool surfaces these so authors can see at a glance
    how their template is being consumed.
    """

    lifetime_completions = serializers.SerializerMethodField()
    active_instances = serializers.SerializerMethodField()

    class Meta(MissionTemplateSerializer.Meta):
        fields = [
            *MissionTemplateSerializer.Meta.fields,
            "lifetime_completions",
            "active_instances",
        ]

    def get_lifetime_completions(self, obj: MissionTemplate) -> int:
        return MissionInstance.objects.filter(template=obj, status=MissionStatus.COMPLETE).count()

    def get_active_instances(self, obj: MissionTemplate) -> list[dict]:
        """Flatten ACTIVE runs into the response — one row per instance.

        SharedMemoryModel identity map keeps current_node + participants
        FK-cached after the prefetch; the in-Python walk fires no extra
        queries beyond the prefetched ones.
        """
        from django.db.models import Prefetch  # noqa: PLC0415

        from world.missions.models import MissionParticipant  # noqa: PLC0415

        rows: list[dict] = []
        instances = (
            MissionInstance.objects.filter(template=obj, status=MissionStatus.ACTIVE)
            .select_related("current_node")
            .prefetch_related(
                Prefetch(
                    "participants",
                    queryset=MissionParticipant.objects.select_related("character"),
                    to_attr="cached_participants",
                ),
            )
            .order_by("pk")
        )
        for instance in instances:
            current_node_key = instance.current_node.key if instance.current_node else None
            contract_holder = None
            for participant in instance.cached_participants:
                if participant.is_contract_holder:
                    contract_holder = participant.character.db_key
                    break
            rows.append(
                {
                    "instance_id": instance.pk,
                    "current_node_key": current_node_key,
                    "contract_holder": contract_holder,
                }
            )
        return rows


# ---------------------------------------------------------------------------
# D2 editor CRUD serializers — one per nested model. ModelSerializer with
# all editable fields (plus the parent FK so create works through nested
# routes). Validation that depends on the WHOLE GRAPH (entry-node
# uniqueness, route-set completeness) lives in dedicated validate/
# actions (D2.validate) — these serializers only enforce single-row
# invariants the model's clean() already covers.
# ---------------------------------------------------------------------------


class MissionNodeSerializer(serializers.ModelSerializer):
    """Editor CRUD for MissionNode rows.

    ``allowed_riders`` exposes the consequence M2M as a list of PKs (the
    authoring UI passes them through unchanged). Editor layout fields
    (editor_x / editor_y) round-trip; flavor_text and its needs_rewrite
    sibling are both editable.
    """

    class Meta:
        model = MissionNode
        fields = [
            "id",
            "template",
            "key",
            "is_entry",
            "conflict_mode",
            "joint_combine",
            "joint_count",
            "allowed_riders",
            "deny_all_riders",
            "editor_x",
            "editor_y",
            "flavor_text",
            "flavor_text_needs_rewrite",
        ]
        read_only_fields = ["id"]


class MissionOptionSerializer(serializers.ModelSerializer):
    """Editor CRUD for MissionOption rows (authored or challenge-sourced).

    Both source_kind values are editable; consumer code distinguishes via
    the kind field (BRANCH vs CHECK). visibility_rule is a JSONField that
    rides through; the predicate-tree builder API (D5) is what authors
    actually use to write it.
    """

    class Meta:
        model = MissionOption
        fields = [
            "id",
            "node",
            "order",
            "option_kind",
            "source_kind",
            "visibility_rule",
            "authored_check_type",
            "authored_base_risk",
            "authored_ic_framing",
            "authored_ic_framing_needs_rewrite",
            "branch_target",
            "challenge",
        ]
        read_only_fields = ["id"]


class MissionOptionRouteSerializer(serializers.ModelSerializer):
    """Editor CRUD for MissionOptionRoute rows (one per outcome tier per option)."""

    class Meta:
        model = MissionOptionRoute
        fields = [
            "id",
            "option",
            "outcome_tier",
            "target_node",
            "is_random_set",
            "consequence",
            "outcome_text",
            "outcome_text_needs_rewrite",
        ]
        read_only_fields = ["id"]


class MissionOptionRouteCandidateSerializer(serializers.ModelSerializer):
    """Editor CRUD for MissionOptionRouteCandidate (random-set rolls)."""

    class Meta:
        model = MissionOptionRouteCandidate
        fields = [
            "id",
            "route",
            "target_node",
            "weight",
            "consequence",
            "outcome_text",
            "outcome_text_needs_rewrite",
        ]
        read_only_fields = ["id"]


class MissionOptionRouteRewardSerializer(serializers.ModelSerializer):
    """Editor CRUD for reward lines attached to a route OR a candidate (XOR).

    Model-level CheckConstraint + clean() both enforce exactly-one-parent.
    DRF's ModelSerializer skips clean() by default, so we mirror the XOR
    check here as ``validate()`` to surface a clean 400 instead of letting
    the DB constraint raise IntegrityError → 500.
    """

    class Meta:
        model = MissionOptionRouteReward
        fields = ["id", "route", "candidate", "kind", "sink", "amount"]
        read_only_fields = ["id"]

    # Module-level constants for the XOR validation messages — avoid
    # inline string literals in raise statements (TRY003/EM101).
    _ERR_BOTH_NULL = "Exactly one of route or candidate must be set; both are null."
    _ERR_BOTH_SET = "Cannot set both route and candidate — pick one."

    def validate(self, attrs: dict) -> dict:
        # Honor partial updates: fall back to instance values for fields
        # not in attrs (PATCH).
        instance = self.instance
        route = attrs.get("route")
        if route is None and instance is not None:
            route = instance.route
        candidate = attrs.get("candidate")
        if candidate is None and instance is not None:
            candidate = instance.candidate
        if route is None and candidate is None:
            raise serializers.ValidationError(self._ERR_BOTH_NULL)
        if route is not None and candidate is not None:
            raise serializers.ValidationError(self._ERR_BOTH_SET)
        return attrs


# Mission giver editor surfaces moved to world.npc_services.* per #686.
# Trigger-based mission givers (ROOM_TRIGGER / ENVIRONMENTAL_DETAIL) still
# use MissionGiver; their editor will land with the trigger followup.


class MissionInstanceSerializer(serializers.ModelSerializer):
    """Staff-side serializer for MissionInstance (assign + remove surfaces).

    Read-only for the common fields; the staff-assign action wraps the
    `staff_assign_mission` service to populate these (so authors don't
    POST to this endpoint to create instances — assign is a deliberate
    operator gesture).
    """

    class Meta:
        model = MissionInstance
        fields = [
            "id",
            "template",
            "current_node",
            "status",
            "started_at",
            "completed_at",
            "source_beat",
        ]
        read_only_fields = ["id", "started_at"]


class MissionCategorySerializer(serializers.ModelSerializer):
    """List + detail serializer for MissionCategory browse.

    Read-only resource exposed via MissionCategoryViewSet; categories
    are seeded via fixture/admin, not authored through the API.
    """

    class Meta:
        model = MissionCategory
        fields = ["id", "name", "description", "display_order"]
        read_only_fields = ["id"]


class MissionGiverSerializer(serializers.ModelSerializer):
    """Staff CRUD for trigger-based MissionGiver rows (#729).

    Covers the two surviving GiverKind variants (ROOM_TRIGGER,
    ENVIRONMENTAL_DETAIL). ``templates`` is a flat M2M draw pool — each
    template self-gates at draw time via its own ``availability_rule``
    (Option A), so there are no per-attachment overrides here.
    """

    is_publishable = serializers.BooleanField(read_only=True)

    class Meta:
        model = MissionGiver
        fields = [
            "id",
            "name",
            "giver_kind",
            "target",
            "org",
            "is_active",
            "templates",
            "is_publishable",
        ]
        read_only_fields = ["id", "is_publishable"]

    def validate(self, attrs: dict) -> dict:
        """Run the model's (kind, target) typeclass check so a bad pairing is a
        400, not a 500 raised from ``save()``."""
        merged = {**({} if self.instance is None else _instance_attrs(self.instance)), **attrs}
        probe = MissionGiver(
            name=merged.get("name", ""),
            giver_kind=merged.get("giver_kind", ""),
            target=merged.get("target"),
            org=merged.get("org"),
            is_active=merged.get("is_active", True),
        )
        try:
            probe.clean()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            raise serializers.ValidationError(detail) from exc
        return attrs


def _instance_attrs(instance: MissionGiver) -> dict:
    """Current persisted field values for a partial-update clean() probe."""
    return {
        "name": instance.name,
        "giver_kind": instance.giver_kind,
        "target": instance.target,
        "org": instance.org,
        "is_active": instance.is_active,
    }


# ---------------------------------------------------------------------------
# #885 player journal/beat surface — read-only serializers over the frozen
# dataclasses from services.journal / services.play (never model-bound; the
# service layer owns the shapes).
# ---------------------------------------------------------------------------


class JournalDeedSerializer(serializers.Serializer):
    """Read-only mirror of :class:`world.missions.types.JournalDeed`."""

    node_key = serializers.CharField()
    option_id = serializers.IntegerField()
    outcome_name = serializers.CharField(allow_null=True)
    applied_at = serializers.DateTimeField()


class JournalEntrySerializer(serializers.Serializer):
    """Read-only mirror of :class:`world.missions.types.JournalEntry`."""

    instance_id = serializers.IntegerField()
    template_name = serializers.CharField()
    status = serializers.CharField()
    current_node_key = serializers.CharField(allow_null=True)
    is_contract_holder = serializers.BooleanField()
    deeds = JournalDeedSerializer(many=True)
    summary = serializers.CharField(allow_blank=True)
    epilogue = serializers.CharField(allow_blank=True)
    current_node_flavor = serializers.CharField(allow_blank=True)
    compass_rooms = serializers.ListField(child=serializers.CharField())
    compass_anywhere = serializers.BooleanField()


class BeatOptionSerializer(serializers.Serializer):
    """Read-only mirror of :class:`world.missions.types.BeatOption`."""

    option_id = serializers.IntegerField()
    approach_id = serializers.IntegerField(allow_null=True)
    label = serializers.CharField()
    kind = serializers.CharField()
    check_type_name = serializers.CharField(allow_null=True)
    base_risk = serializers.IntegerField()


class BeatViewSerializer(serializers.Serializer):
    """Read-only mirror of :class:`world.missions.types.BeatView`."""

    instance_id = serializers.IntegerField()
    template_name = serializers.CharField()
    node_key = serializers.CharField()
    flavor_text = serializers.CharField(allow_blank=True)
    options = BeatOptionSerializer(many=True)


class ResolvedBeatSerializer(serializers.Serializer):
    """Read-only mirror of :class:`world.missions.types.ResolvedBeat`."""

    instance_id = serializers.IntegerField()
    outcome_name = serializers.CharField(allow_null=True)
    story_text = serializers.CharField()
    is_terminal = serializers.BooleanField()
    # SerializerMethodField rather than a nested allow_null serializer —
    # DRF nested to_representation does not accept None.
    next_beat = serializers.SerializerMethodField()
    epilogue = serializers.CharField(allow_blank=True)

    @extend_schema_field(BeatViewSerializer(allow_null=True))
    def get_next_beat(self, obj: object) -> dict | None:
        beat = obj.next_beat  # type: ignore[attr-defined]
        return BeatViewSerializer(beat).data if beat is not None else None


class BeatResolveRequestSerializer(serializers.Serializer):
    """POST body for the #885 resolve endpoint."""

    option_id = serializers.IntegerField(min_value=1)
    approach_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
