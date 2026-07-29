"""Serializers for the tasking API (#2820 phase 1)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.tasking.models import (
    ListenerPost,
    OrgTask,
    TaskFulfillment,
    TaskOutcomeRoute,
    TaskTemplate,
)


class TaskTemplateSerializer(serializers.ModelSerializer):
    """Staff authoring surface for job templates."""

    class Meta:
        model = TaskTemplate
        fields = [
            "id",
            "name",
            "description",
            "category",
            "check_type",
            "check_difficulty",
            "duration",
            "target_kind",
            "eligibility_rule",
            "mission_template",
            "consequence_pool",
            "is_active",
        ]


class TaskOutcomeRouteSerializer(serializers.ModelSerializer):
    """Staff authoring surface for per-tier payout routes."""

    class Meta:
        model = TaskOutcomeRoute
        fields = [
            "id",
            "template",
            "outcome_tier",
            "money_reward",
            "clue_pool",
            "report_template",
            # Spy Job Kit payouts (#2833).
            "movements_report",
            "unmask_target",
            "gossip_heat_delta",
            "building_condition_delta",
            "recruit_target",
            "incriminate_level",
            # Cross-system payouts (#2833 addendum).
            "domain_report",
            "domain_unrest_delta",
            "organization_report",
            "military_report",
            # Threat-loop payouts (#2837).
            "reveal_schemes",
            "crisis_severity_delta",
            "exploit_crisis",
        ]


class TaskTemplateSummarySerializer(serializers.ModelSerializer):
    """Read-only template summary embedded in board rows."""

    class Meta:
        model = TaskTemplate
        fields = ["id", "name", "description", "category", "duration", "target_kind"]


class TaskFulfillmentSerializer(serializers.ModelSerializer):
    """Board row detail: who is on the job and, once resolved, the report."""

    handler_name = serializers.CharField(source="handler.name", read_only=True)
    agent_name = serializers.SerializerMethodField()
    report = serializers.SerializerMethodField()
    resolved_outcome_name = serializers.SerializerMethodField()

    class Meta:
        model = TaskFulfillment
        fields = [
            "id",
            "handler",
            "handler_name",
            "agent_name",
            "is_active",
            "assigned_at",
            "resolved_at",
            "resolved_outcome_name",
            "report",
        ]

    def get_agent_name(self, obj: TaskFulfillment) -> str:
        return str(obj.npc_asset.asset_persona) if obj.npc_asset_id else ""

    def get_report(self, obj: TaskFulfillment) -> str:
        """The agent's report is readable only once the job resolved."""
        return obj.report if obj.resolved_at is not None else ""

    def get_resolved_outcome_name(self, obj: TaskFulfillment) -> str:
        return str(obj.resolved_outcome.name) if obj.resolved_outcome_id else ""


class OrgTaskSerializer(serializers.ModelSerializer):
    """Board row: a live task with its template summary and fulfillment."""

    template = TaskTemplateSummarySerializer(read_only=True)
    target_label = serializers.SerializerMethodField()
    fulfillment = serializers.SerializerMethodField()

    class Meta:
        model = OrgTask
        fields = [
            "id",
            "template",
            "org",
            "issued_by",
            "status",
            "deadline",
            "target_kind",
            "target_label",
            "created_at",
            "resolved_at",
            "fulfillment",
        ]

    def get_target_label(self, obj: OrgTask) -> str:
        from world.tasking.services import target_label  # noqa: PLC0415

        return target_label(obj)

    @extend_schema_field(TaskFulfillmentSerializer(allow_null=True))
    def get_fulfillment(self, obj: OrgTask) -> dict | None:
        by_task = self.context.get("active_fulfillments_by_task")
        if by_task is not None:
            active = by_task.get(obj.pk)
        else:
            active = (
                obj.fulfillments.filter(is_active=True)
                .select_related("handler", "npc_asset__asset_persona", "resolved_outcome")
                .first()
            )
        if active is None:
            return None
        return TaskFulfillmentSerializer(active, context=self.context).data


class ListenerPostSerializer(serializers.ModelSerializer):
    """Board row for a standing listener post.

    The buzz meter is shown as-is: a suppressed post (phase 4) and an
    unlucky one render identically — the ambiguity is the design.
    """

    agent_name = serializers.SerializerMethodField()
    room_id = serializers.IntegerField(source="assignment.room_id", read_only=True)
    handler_name = serializers.CharField(source="handler.name", read_only=True)
    pending_harvests = serializers.SerializerMethodField()

    class Meta:
        model = ListenerPost
        fields = [
            "id",
            "agent_name",
            "room_id",
            "handler",
            "handler_name",
            "buzz",
            "threshold",
            "last_sweep_at",
            "pending_harvests",
            "created_at",
        ]

    def get_agent_name(self, obj) -> str:
        asset = obj.assignment.npc_asset
        return str(asset.asset_persona) if asset else ""

    def get_pending_harvests(self, obj) -> int:
        return obj.harvests.filter(collected_at__isnull=True).count()


class ListenerPostCreateSerializer(serializers.Serializer):
    """Create payload: agent + room; optional tradecraft check."""

    npc_asset = serializers.IntegerField(min_value=1)
    room = serializers.IntegerField(min_value=1)
    check_type = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    check_difficulty = serializers.IntegerField(default=0)


class PlantRedHerringSerializer(serializers.Serializer):
    """Plant payload: the flipped post, the mark, and the lie."""

    post = serializers.IntegerField(min_value=1)
    subject_sheet = serializers.IntegerField(min_value=1)
    content = serializers.CharField(max_length=2000)


class OrgTaskCreateSerializer(serializers.ModelSerializer):
    """Create payload: template + org + the target leg matching the template."""

    class Meta:
        model = OrgTask
        fields = [
            "template",
            "org",
            "target_room",
            "target_org",
            "target_domain",
            "target_persona",
            "target_crisis",
        ]


class TaskAssignSerializer(serializers.Serializer):
    """Assign payload: the agent to dispatch (handler = requester, phase 1)."""

    npc_asset = serializers.IntegerField(min_value=1)
