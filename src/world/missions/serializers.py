"""DRF serializers for the missions authoring API (Phase D).

D1 ships ``MissionTemplateSerializer`` (list + detail browse). Editor
CRUD serializers for nodes / options / routes / candidates / rewards
land in D2; giver-library serializers in D3; predicate-tree in D5.
"""

from rest_framework import serializers

from world.missions.constants import MissionStatus
from world.missions.models import (
    MissionInstance,
    MissionNode,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionOptionRouteReward,
    MissionTemplate,
)


class MissionTemplateSerializer(serializers.ModelSerializer):
    """List + detail serializer for MissionTemplate browse.

    Read-only fields cover the authoring footprint: name, slug, summary,
    epilogue, level band, risk tier, weighting, era association, scope,
    cooldown, reward-group rule, active flag, access tier, categories,
    availability rule. The ``categories`` M2M is serialized as a list of
    category names — categories are lookup rows with unique names.

    Editor CRUD (D2) reuses this serializer for create/update via
    ModelViewSet write paths; per the project's "Validation belongs in
    serializers, not views or services" rule, additional graph
    well-formedness validation lands here as ``validate()`` methods when
    D2 introduces those constraints.
    """

    categories = serializers.SlugRelatedField(
        many=True,
        slug_field="name",
        read_only=True,
    )

    class Meta:
        model = MissionTemplate
        fields = [
            "id",
            "name",
            "slug",
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
            "access_tier",
            "categories",
            "availability_rule",
        ]
        read_only_fields = ["id"]


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
