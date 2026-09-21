"""Serializers for the tie API (#3957)."""

from rest_framework import serializers

from world.relationships.constants import LabelAwareness
from world.relationships.models import (
    RelationshipCapstone,
    RelationshipCondition,
    RelationshipLabel,
    RelationshipType,
)


class RelationshipConditionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RelationshipCondition
        fields = ["id", "name", "description", "display_order"]


class RelationshipTypeSerializer(serializers.ModelSerializer):
    counterpart_name = serializers.CharField(
        source="counterpart.name", read_only=True, default=None
    )

    class Meta:
        model = RelationshipType
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "family",
            "valence",
            "counterpart",
            "counterpart_name",
            "display_order",
        ]


class RelationshipLabelSerializer(serializers.ModelSerializer):
    type_name = serializers.CharField(source="type.name", read_only=True)
    type_family = serializers.CharField(source="type.family", read_only=True)
    type_valence = serializers.CharField(source="type.valence", read_only=True)
    replaced_type_name = serializers.CharField(
        source="replaced.type.name", read_only=True, default=None
    )
    is_mutual = serializers.BooleanField(read_only=True)

    class Meta:
        model = RelationshipLabel
        fields = [
            "id",
            "type",
            "type_name",
            "type_family",
            "type_valence",
            "awareness",
            "since",
            "ended_at",
            "replaced_type_name",
            "note",
            "is_mutual",
        ]


class DepthBreakdownSerializer(serializers.Serializer):
    tier = serializers.IntegerField()
    scenes = serializers.IntegerField()
    invested = serializers.IntegerField()
    their_added_depth = serializers.IntegerField()
    affection = serializers.IntegerField(allow_null=True)
    conflict = serializers.IntegerField(allow_null=True)


class TieThreadSerializer(serializers.Serializer):
    level = serializers.IntegerField()
    resonance_name = serializers.CharField()


class TieSerializer(serializers.Serializer):
    """One side of a tie, shaped for the viewer's audience (built in the viewset)."""

    id = serializers.IntegerField()
    source = serializers.IntegerField()
    target = serializers.IntegerField(allow_null=True)
    target_companion = serializers.IntegerField(allow_null=True)
    target_name = serializers.CharField()
    other_sheet_id = serializers.IntegerField(allow_null=True)
    other_entry_id = serializers.IntegerField(allow_null=True)
    audience = serializers.CharField()
    labels = RelationshipLabelSerializer(many=True)
    depth = serializers.IntegerField(allow_null=True)
    next_tier_threshold = serializers.IntegerField(allow_null=True)
    breakdown = DepthBreakdownSerializer(allow_null=True)
    summary = serializers.CharField(allow_blank=True)
    ap_this_week = serializers.IntegerField(allow_null=True)
    thread = TieThreadSerializer(allow_null=True)
    is_soul_tether = serializers.BooleanField()


class TieStreamItemSerializer(serializers.Serializer):
    kind = serializers.CharField()
    id = serializers.IntegerField()
    title = serializers.CharField()
    author_id = serializers.IntegerField(allow_null=True)
    author_name = serializers.CharField(allow_blank=True)
    body = serializers.CharField(allow_blank=True)
    is_public = serializers.BooleanField()
    capstone_tier = serializers.IntegerField(allow_null=True)
    created_at = serializers.CharField()
    ic_timestamp = serializers.CharField(allow_null=True)


class RelationshipCapstoneSerializer(serializers.ModelSerializer):
    title = serializers.CharField(read_only=True)
    journal_entry_title = serializers.CharField(
        source="journal_entry.title", read_only=True, default=None
    )

    class Meta:
        model = RelationshipCapstone
        fields = [
            "id",
            "relationship",
            "journal_entry",
            "journal_entry_title",
            "title",
            "tier_claimed",
            "xp_spent",
            "is_ritual_capstone",
            "created_at",
        ]


class RelationshipTargetWriteSerializer(serializers.Serializer):
    target_persona_id = serializers.IntegerField(required=False)
    target_companion_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if (attrs.get("target_persona_id") is not None) == (
            attrs.get("target_companion_id") is not None
        ):
            msg = "Provide exactly one of target_persona_id or target_companion_id."
            raise serializers.ValidationError(msg)
        return attrs


class DeclareWriteSerializer(RelationshipTargetWriteSerializer):
    type_id = serializers.IntegerField()
    awareness = serializers.ChoiceField(
        choices=LabelAwareness.choices, default=LabelAwareness.PRIVATE
    )


class LabelWriteSerializer(serializers.Serializer):
    label_id = serializers.IntegerField()


class ShiftWriteSerializer(LabelWriteSerializer):
    new_type_id = serializers.IntegerField()
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=200)


class AwarenessWriteSerializer(LabelWriteSerializer):
    awareness = serializers.ChoiceField(choices=LabelAwareness.choices)


class AllocationWriteSerializer(RelationshipTargetWriteSerializer):
    ap_amount = serializers.IntegerField(min_value=0)


class AdvanceWriteSerializer(RelationshipTargetWriteSerializer):
    journal_entry_id = serializers.IntegerField()


class SummaryWriteSerializer(RelationshipTargetWriteSerializer):
    summary = serializers.CharField(allow_blank=True, max_length=4000)
