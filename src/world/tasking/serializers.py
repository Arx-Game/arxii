"""Serializers for the tasking API (#2820 phase 1)."""

from __future__ import annotations

from rest_framework import serializers

from world.tasking.models import OrgTask, TaskFulfillment, TaskOutcomeRoute, TaskTemplate


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
        ]


class TaskAssignSerializer(serializers.Serializer):
    """Assign payload: the agent to dispatch (handler = requester, phase 1)."""

    npc_asset = serializers.IntegerField(min_value=1)
