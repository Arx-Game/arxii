"""Explicit safe wire projections for typed menu reads."""

from typing import Any

from rest_framework import serializers

from actions.serializers import ActionRefSerializer, PlayerActionSerializer
from actions.target_menu_types import AUTHOR_ENTRY_CONTEXT, MenuTargetKind

GROUP_KEYS = ("perception", "items", "movement", "authored")
CANDIDATE_KIND_CONTEXT = "candidate_kind"
INPUT_DESCRIPTOR = "descriptor"
INPUT_BLEND = "blend"
ENTRY_KWARG_KEYS = {
    AUTHOR_ENTRY_CONTEXT: frozenset(),
    "look_at_item": frozenset({"menu_target"}),
    "look": frozenset({"menu_target"}),
    "get": frozenset({"menu_target"}),
    "drop": frozenset({"menu_target"}),
    "equip": frozenset({"menu_target"}),
    "unequip": frozenset({"menu_target"}),
    "give": frozenset({"menu_target"}),
    "put_in": frozenset({"menu_target"}),
    "take_out": frozenset({"menu_target"}),
    "steal": frozenset({"menu_target"}),
    "use_item": frozenset({"menu_target", "descriptor", "blend"}),
    "join_place": frozenset({"menu_target"}),
    "leave_place": frozenset({"menu_target"}),
    "traverse_exit": frozenset({"menu_target"}),
}
CANDIDATE_KWARG_KEYS = {
    ("give", "recipient"): frozenset({"recipient_persona_id"}),
    ("put_in", "container"): frozenset({"container_item_id"}),
    ("use_item", "combination"): frozenset({"use_target", "option_id", "descriptor", "blend"}),
}
CANDIDATE_KINDS = {"give": "recipient", "put_in": "container", "use_item": "combination"}


class MenuTargetSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[kind.value for kind in MenuTargetKind])
    target_id = serializers.IntegerField(min_value=1)
    owner_persona_id = serializers.IntegerField(min_value=1, required=False)
    container_item_id = serializers.IntegerField(min_value=1, required=False)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        invalid = set(data).difference(self.fields)
        if invalid:
            raise serializers.ValidationError(
                {key: ["Not allowed in a menu target."] for key in sorted(invalid)}
            )
        return super().to_internal_value(data)


class MenuUseTargetSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("items", "objects"))
    target_id = serializers.IntegerField(min_value=1)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        invalid = set(data).difference(self.fields)
        if invalid:
            raise serializers.ValidationError(
                {key: ["Not allowed in a Use target."] for key in sorted(invalid)}
            )
        return super().to_internal_value(data)


class MenuKwargsSerializer(serializers.Serializer):
    menu_target = MenuTargetSerializer(required=False)
    recipient_persona_id = serializers.IntegerField(min_value=1, required=False)
    container_item_id = serializers.IntegerField(min_value=1, required=False)
    use_target = MenuUseTargetSerializer(required=False)
    option_id = serializers.IntegerField(min_value=1, required=False)
    descriptor = serializers.CharField(required=False, trim_whitespace=False)
    blend = serializers.BooleanField(required=False)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        """Reject raw misplaced keys and non-typed cosmetic values before field coercion."""
        action_key = self.context["action_key"]
        candidate_kind = self.context.get("candidate_kind")
        allowed = (
            CANDIDATE_KWARG_KEYS.get((action_key, candidate_kind), frozenset())
            if CANDIDATE_KIND_CONTEXT in self.context
            else ENTRY_KWARG_KEYS[action_key]
        )
        invalid = set(data).difference(allowed)
        if invalid:
            raise serializers.ValidationError(
                {key: ["Not allowed for this action/candidate."] for key in sorted(invalid)}
            )
        errors = {}
        if INPUT_DESCRIPTOR in data and not isinstance(data[INPUT_DESCRIPTOR], str):
            errors[INPUT_DESCRIPTOR] = ["Enter text."]
        if INPUT_BLEND in data and type(data[INPUT_BLEND]) is not bool:
            errors[INPUT_BLEND] = ["Enter a boolean."]
        if errors:
            raise serializers.ValidationError(errors)
        return super().to_internal_value(data)

    def to_representation(self, instance: Any) -> dict[str, Any]:
        """Fail closed on internal output as well as explicit input validation."""
        validated = self.to_internal_value(instance)
        return super().to_representation(validated)


class MenuInputSerializer(serializers.Serializer):
    name = serializers.ChoiceField(
        choices=(
            "recipient_persona_id",
            "container_item_id",
            "use_target",
            "option_id",
            "descriptor",
            "blend",
        )
    )
    kind = serializers.ChoiceField(
        choices=("recipient", "container", "target", "option", "text", "boolean")
    )
    required = serializers.BooleanField()
    target_kind = serializers.CharField(allow_null=True)
    default = serializers.JSONField()


class MenuCandidateSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    kwargs = MenuKwargsSerializer()
    available = serializers.BooleanField()
    reasons = serializers.ListField(child=serializers.CharField())


class MenuRiskOutcomeSerializer(serializers.Serializer):
    stage = serializers.CharField()
    tier = serializers.CharField()
    character_loss = serializers.BooleanField()


class MenuRiskSerializer(serializers.Serializer):
    known = serializers.BooleanField()
    character_loss_possible = serializers.BooleanField(allow_null=True)
    outcomes = MenuRiskOutcomeSerializer(many=True)


class MenuEntryListSerializer(serializers.ListSerializer):
    def to_representation(self, data: Any) -> list[dict[str, Any]]:
        """Bind independent internal action context for each explicit entry schema."""
        return [
            MenuEntrySerializer(row, context={"action_key": row["action_key"]}).data for row in data
        ]


class MenuEntrySerializer(serializers.Serializer):
    class Meta:
        list_serializer_class = MenuEntryListSerializer

    key = serializers.CharField()
    label = serializers.CharField()
    group = serializers.ChoiceField(choices=GROUP_KEYS)
    ref = ActionRefSerializer()
    kwargs = MenuKwargsSerializer()
    available = serializers.BooleanField()
    reasons = serializers.ListField(child=serializers.CharField())
    inputs = MenuInputSerializer(many=True)
    candidates = serializers.SerializerMethodField()
    next_candidate_cursor = serializers.CharField(allow_null=True)
    action = PlayerActionSerializer(allow_null=True)
    risk = MenuRiskSerializer(allow_null=True)

    def get_candidates(self, obj: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate each complete candidate with independent action/kind context."""
        action_key = self.context["action_key"]
        return [
            MenuCandidateSerializer(
                row,
                context={
                    "action_key": action_key,
                    CANDIDATE_KIND_CONTEXT: CANDIDATE_KINDS.get(action_key),
                },
            ).data
            for row in obj["candidates"]
        ]


class MenuGroupSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=GROUP_KEYS)
    label = serializers.CharField()


class TargetMenuSerializer(serializers.Serializer):
    actor_id = serializers.IntegerField()
    target = MenuTargetSerializer()
    label = serializers.CharField()
    groups = MenuGroupSerializer(many=True)
    entries = MenuEntrySerializer(many=True)
