"""Serializers for the checks API."""

from __future__ import annotations

from dataclasses import asdict

from rest_framework import serializers

from world.checks.consequence_resolution import resolve_pool_consequences
from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier
from world.checks.outcome_utils import build_outcome_display


class ConsequenceOutcomeModifierSerializer(serializers.ModelSerializer):
    """Serializes a single snapshotted modifier contribution."""

    class Meta:
        model = ConsequenceOutcomeModifier
        fields = ["source_kind", "source_label", "value"]


class ConsequenceOutcomeSerializer(serializers.ModelSerializer):
    """Read serializer for ConsequenceOutcome.

    Recomputes the roulette display on every read from the persisted pool +
    selected_consequence so the frontend always receives the full weighted
    roulette (outcome_display) rather than storing it.

    combat_interaction and challenge_record are exposed as plain integer ids to
    avoid touching the range-partitioned scenes_interaction table at
    serialization time.
    """

    modifiers = ConsequenceOutcomeModifierSerializer(many=True, read_only=True)
    outcome_display = serializers.SerializerMethodField()
    combat_interaction_id = serializers.IntegerField(read_only=True)
    challenge_record_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ConsequenceOutcome
        fields = [
            "id",
            "character",
            "check_type",
            "pool",
            "selected_consequence",
            "modifier_total",
            "summary",
            "outcome_display",
            "modifiers",
            "combat_interaction_id",
            "challenge_record_id",
            "created_at",
        ]
        read_only_fields = fields

    def get_outcome_display(self, obj: ConsequenceOutcome) -> list[dict]:
        """Recompute the roulette from pool + selected_consequence on read.

        Uses resolve_pool_consequences() — the same pool-walk used by
        apply_pool_deterministically — to get the full flat list of
        Consequence rows, then passes them with the persisted
        selected_consequence to build_outcome_display() to mark the winner.

        Returns a list of plain dicts matching OutcomeDisplay's fields.
        """
        all_consequences = resolve_pool_consequences(obj.pool)
        display_items = build_outcome_display(all_consequences, obj.selected_consequence)
        return [asdict(item) for item in display_items]
