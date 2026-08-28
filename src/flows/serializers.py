"""Serializers for the flows authoring API (#3417 task 4).

``FlowDefinitionWriteSerializer`` accepts a client-authored step tree (nodes
addressed by an author-chosen ``client_id``, not a DB pk — the tree may
contain brand-new steps alongside a rename of existing ones) and replaces the
flow's entire step set depth-first so the saved rows read back in the same
order the author built them in. Validation is catalog-driven
(``flows.step_validation.validate_step_tree``) so an author can never save a
tree the runtime would choke on.
"""

from collections import defaultdict
from typing import Any

from rest_framework import serializers

from flows.consts import FlowActionChoices
from flows.interactions import flow_interactions
from flows.models import FlowDefinition, FlowStepDefinition
from flows.step_validation import validate_step_tree


class FlowStepWriteSerializer(serializers.Serializer):
    """One authored step, addressed by a client-chosen id rather than a pk."""

    client_id = serializers.CharField(max_length=64)
    parent_client_id = serializers.CharField(
        max_length=64, required=False, allow_null=True, default=None
    )
    action = serializers.ChoiceField(choices=FlowActionChoices.choices)
    variable_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    parameters = serializers.JSONField(required=False, default=dict)

    def validate_parameters(self, value: Any) -> dict[str, Any]:
        """Reject a non-dict payload before it ever reaches ``validate_step_tree``.

        ``JSONField`` accepts any JSON-serializable value (a list, a string, a
        number); ``validate_step_tree``/``_check_step_against_spec`` assumes
        ``parameters`` is a mapping and calls ``.items()`` on it, which raises
        an unhandled ``AttributeError`` for anything else. Catching the shape
        mismatch here turns that crash into an ordinary 400 field error.
        """
        if not isinstance(value, dict):
            msg = "parameters must be a JSON object."
            raise serializers.ValidationError(msg)
        return value


class FlowDefinitionWriteSerializer(serializers.ModelSerializer):
    """Create/update payload: flow fields plus an optional full step tree.

    ``steps`` omitted from the request body means "leave the existing steps
    untouched" (update only — create always starts from an empty tree);
    ``steps: []`` or a populated list means "replace the entire tree with
    this."
    """

    # write_only: FlowStepWriteSerializer's fields (client_id, parent_client_id)
    # are client-authoring concepts with no matching FlowStepDefinition model
    # attribute, so echoing this field back via to_representation() on the
    # saved instance would raise AttributeError. The canonical read-back of a
    # saved tree is GET .../{pk}/ (FlowDefinitionDetailSerializer), which
    # serializes real FlowStepDefinition rows instead.
    steps = FlowStepWriteSerializer(many=True, required=False, write_only=True)

    class Meta:
        model = FlowDefinition
        fields = ["id", "name", "description", "steps"]

    def validate_steps(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        validate_step_tree(value)  # ValidationError propagates as a field error
        return value

    def create(self, validated_data: dict[str, Any]) -> FlowDefinition:
        steps = validated_data.pop("steps", [])
        flow = FlowDefinition.objects.create(**validated_data)
        _replace_steps(flow, steps)
        return flow

    def update(self, instance: FlowDefinition, validated_data: dict[str, Any]) -> FlowDefinition:
        steps = validated_data.pop("steps", None)
        instance = super().update(instance, validated_data)
        if steps is not None:
            _replace_steps(instance, steps)
        return instance


def _replace_steps(flow: FlowDefinition, steps_data: list[dict[str, Any]]) -> None:
    """Full-tree replace, inserting depth-first so queryset order == authored order."""
    flow.steps.all().delete()
    children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for step in steps_data:
        children[step.get("parent_client_id")].append(step)

    def _insert(parent_key: str | None, parent_obj: FlowStepDefinition | None) -> None:
        for step in children.get(parent_key, []):
            obj = FlowStepDefinition.objects.create(
                flow=flow,
                parent=parent_obj,
                action=step["action"],
                variable_name=step.get("variable_name", ""),
                parameters=step.get("parameters") or {},
            )
            _insert(step["client_id"], obj)

    _insert(None, None)


class FlowStepReadSerializer(serializers.ModelSerializer):
    """One saved step, as returned by ``FlowDefinitionViewSet.retrieve``."""

    class Meta:
        model = FlowStepDefinition
        fields = ["id", "parent", "action", "variable_name", "parameters"]


class FlowDefinitionListSerializer(serializers.ModelSerializer):
    """Row shape for ``FlowDefinitionViewSet.list`` — no step bodies.

    ``step_count`` is sourced from an ``annotate(step_count=Count("steps"))``
    on the viewset's queryset rather than a per-row ``.steps.count()`` call,
    per the no-queries-in-loops rule.
    """

    step_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = FlowDefinition
        fields = ["id", "name", "description", "step_count"]


class FlowDefinitionDetailSerializer(serializers.ModelSerializer):
    """Row shape for ``FlowDefinitionViewSet.retrieve`` — full step tree.

    Reads from ``prefetched_steps`` (the ``Prefetch(..., to_attr=...)`` the
    viewset's queryset populates, explicitly ordered by pk so this always
    reflects the depth-first authored order ``_replace_steps`` inserted in)
    rather than the bare ``steps`` related manager, which would re-query with
    no explicit ordering. ``interactions`` cross-references what runs this
    flow, what it emits (and who listens), and what it calls — see
    ``flows.interactions.flow_interactions``.
    """

    steps = FlowStepReadSerializer(many=True, read_only=True, source="prefetched_steps")
    interactions = serializers.SerializerMethodField()

    class Meta:
        model = FlowDefinition
        fields = ["id", "name", "description", "steps", "interactions"]

    def get_interactions(self, instance: FlowDefinition) -> dict[str, Any]:
        return flow_interactions(instance)
