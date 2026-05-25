"""DRF serializers for the missions authoring API (Phase D).

D1 ships ``MissionTemplateSerializer`` (list + detail browse). Editor
CRUD serializers for nodes / options / routes / candidates / rewards
land in D2; giver-library serializers in D3; predicate-tree in D5.
"""

from rest_framework import serializers

from world.missions.constants import MissionStatus
from world.missions.models import MissionInstance, MissionTemplate


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
            for participant in instance.cached_participants:  # noqa: PREFETCH_STRING — to_attr above
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
