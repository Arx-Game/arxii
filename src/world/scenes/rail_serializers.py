"""Response-shape serializers for GET /api/scenes/{id}/gm-rail/ (#3434).

Documentation-only (drf_spectacular schema) - the view builds the payload via
``world.scenes.rail_services.build_gm_story_rail_payload`` and returns it as a
plain dict; these serializers describe that dict's shape for the OpenAPI
schema and are not used to validate writes (the endpoint has none).
"""

from __future__ import annotations

from rest_framework import serializers

from world.stories.serializers import (
    BeatOpponentLineSerializer,
    BeatStagedTemplateSerializer,
    StoryProtectedSubjectSerializer,
)


class GMStoryRailBeatSerializer(serializers.Serializer):
    """The running beat's authored state, gated per-field by story standing."""

    id = serializers.IntegerField()
    kind = serializers.CharField()
    risk = serializers.CharField()
    outcome = serializers.CharField()
    predicate_type = serializers.CharField()
    success_consequences_authored = serializers.BooleanField()
    failure_consequences_authored = serializers.BooleanField()
    expired_consequences_authored = serializers.BooleanField()
    internal_description = serializers.CharField(allow_null=True)
    opponent_lines = BeatOpponentLineSerializer(many=True, allow_null=True)
    staged_templates = BeatStagedTemplateSerializer(many=True, allow_null=True)


class GMStoryRailStakeOutcomeSerializer(serializers.Serializer):
    """The fired branch for one stake, if the contract has resolved it."""

    column = serializers.CharField()
    outcome_key = serializers.CharField()
    resolution_summary = serializers.CharField()


class GMStoryRailStakeSerializer(serializers.Serializer):
    """One stake on the running beat's contract, story-standing viewers only."""

    id = serializers.IntegerField()
    player_summary = serializers.CharField()
    severity = serializers.IntegerField()
    subject_kind = serializers.CharField()
    outcome = GMStoryRailStakeOutcomeSerializer(allow_null=True)


class GMStoryRailActivationSerializer(serializers.Serializer):
    """The running beat's lock state: the open activation, or the most recent
    resolved one when none is open.
    """

    locked_at = serializers.DateTimeField()
    effective_risk = serializers.CharField()
    is_ready = serializers.BooleanField()


class GMStoryRailParticipantSerializer(serializers.Serializer):
    """One character currently present in the scene's room (location-derived)."""

    character_sheet_id = serializers.IntegerField()
    name = serializers.CharField()


class GMStoryRailClueSerializer(serializers.Serializer):
    """One room clue placement - staff viewers only."""

    id = serializers.IntegerField()
    clue_name = serializers.CharField()
    detect_difficulty = serializers.IntegerField()
    is_active = serializers.BooleanField()


class GMStoryRailSerializer(serializers.Serializer):
    """Full GM story rail response."""

    beat = GMStoryRailBeatSerializer(allow_null=True)
    protected_subjects = StoryProtectedSubjectSerializer(many=True)
    clue_placements = GMStoryRailClueSerializer(many=True)
    participants = GMStoryRailParticipantSerializer(many=True)
