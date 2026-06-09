"""Serializers for the checks API."""

from __future__ import annotations

from dataclasses import asdict

from rest_framework import serializers

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

        Reads pool entries and parent entries from the prefetch cache
        (populated by the ViewSet's _POOL_ENTRIES_PREFETCH /
        _PARENT_ENTRIES_PREFETCH Prefetch objects) so no additional queries
        are issued per row.  Mirrors the pool-walk logic of
        resolve_pool_consequences() but operates on already-fetched data.

        Returns a list of plain dicts matching OutcomeDisplay's fields.
        """
        pool = obj.pool
        # Read from prefetch cache — pool.entries.all() hits the cache when
        # the ViewSet has declared a Prefetch for "pool__entries".
        own_entries = list(pool.entries.all())

        if pool.parent_id is None:
            all_consequences = [e.consequence for e in own_entries if not e.is_excluded]
        else:
            excluded_ids = {e.consequence_id for e in own_entries if e.is_excluded}
            # pool.parent.entries.all() hits the _PARENT_ENTRIES_PREFETCH cache.
            parent_consequences = [
                e.consequence
                for e in pool.parent.entries.all()
                if e.consequence_id not in excluded_ids
            ]
            own_included = [e.consequence for e in own_entries if not e.is_excluded]
            all_consequences = parent_consequences + own_included

        display_items = build_outcome_display(all_consequences, obj.selected_consequence)
        return [asdict(item) for item in display_items]
