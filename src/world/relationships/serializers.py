"""Serializers for the tie API (#3957)."""

from rest_framework import serializers

from world.relationships.constants import LabelAwareness, TieAudience
from world.relationships.models import (
    RelationshipCapstone,
    RelationshipCondition,
    RelationshipType,
)


class RelationshipConditionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RelationshipCondition
        fields = ["id", "name", "description", "display_order"]
        read_only_fields = fields


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
        read_only_fields = fields


class RelationshipLabelSerializer(serializers.Serializer):
    """One label, as a flat dict built by ``reads.label_payload`` (#3957 review).

    No ``source=`` indirection: the payload builder — not the model instance — computes
    every audience-gated value (``replaced_type_name``, ``note``, ``is_mutual``), since a
    plain model-sourced field can't express "show this only when it clears the viewer's
    audience." Passing a ``RelationshipLabel`` instance here would also mean stamping
    computed attributes onto an idmapper-shared row; a dict avoids that entirely.
    """

    id = serializers.IntegerField()
    type = serializers.IntegerField()
    type_name = serializers.CharField()
    type_family = serializers.CharField()
    type_valence = serializers.CharField()
    awareness = serializers.CharField()
    since = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(allow_null=True)
    replaced_type_name = serializers.CharField(allow_null=True)
    note = serializers.CharField(allow_blank=True)
    is_mutual = serializers.BooleanField()


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


class TieApPoolSerializer(serializers.Serializer):
    """The owner's whole weekly AP purse, as the budget line beside the tie's AP field
    reads it (#3957): what is left to spend over what the week holds.

    Not the same number as ``ap_this_week``, which is this ONE tie's standing order.
    ``remaining`` is ``ActionPointPool.current`` — the spendable balance every other AP
    surface means by "current" — and ``total`` is ``get_effective_maximum()``, so a
    distinction that widens the purse widens this line too.
    """

    remaining = serializers.IntegerField()
    total = serializers.IntegerField()


class TieSerializer(serializers.Serializer):
    """One side of a tie, shaped for the viewer's audience (built in the viewset)."""

    id = serializers.IntegerField()
    source = serializers.IntegerField()
    target = serializers.IntegerField(allow_null=True)
    target_companion = serializers.IntegerField(allow_null=True)
    target_name = serializers.CharField()
    other_sheet_id = serializers.IntegerField(allow_null=True)
    other_entry_id = serializers.IntegerField(allow_null=True)
    audience = serializers.ChoiceField(choices=TieAudience.choices)
    # Whether this side belongs to the viewer's own character — the ONLY thing the web
    # client may gate a write door on (#3957 review). ``audience`` cannot answer it:
    # ``tie_audience`` short-circuits on ``is_staff`` first, so a staff account reading
    # ANY tie gets STAFF, and four of the seven writes resolve their side as
    # ``get_or_create(source=the caller's own sheet, ...)``. Gating on the enum therefore
    # offered staff an Edit/Declare door on someone else's tie whose press wrote a
    # durable row on the staff character's own side.
    is_own_side = serializers.BooleanField()
    labels = RelationshipLabelSerializer(many=True)
    depth = serializers.IntegerField(allow_null=True)
    next_tier_threshold = serializers.IntegerField(allow_null=True)
    breakdown = DepthBreakdownSerializer(allow_null=True)
    summary = serializers.CharField(allow_blank=True)
    ap_this_week = serializers.IntegerField(allow_null=True)
    # The viewer's OWN purse, so it rides ``is_own_side`` rather than ``audience``: a
    # staff account reading someone else's tie has no business being shown that
    # character's balance, and the number would be useless to them anyway — every write
    # door on that page is closed to them.
    ap_pool = TieApPoolSerializer(allow_null=True)
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
    is_capstone = serializers.BooleanField()
    capstone_tier = serializers.IntegerField(allow_null=True)
    created_at = serializers.CharField()
    ic_timestamp = serializers.CharField(allow_null=True)


class TieWriteResultSerializer(serializers.Serializer):
    """The honest shape every tie write action returns (#3957 review) — used only for the
    OpenAPI schema; the views build this dict by hand (``success``/``message``/``data``).
    """

    success = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.DictField()


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
        read_only_fields = fields


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
