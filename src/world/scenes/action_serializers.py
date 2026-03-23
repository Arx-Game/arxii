"""Serializers for scene action requests."""

from __future__ import annotations

from rest_framework import serializers

from world.scenes.action_constants import ConsentDecision
from world.scenes.action_models import SceneActionRequest


class SceneActionRequestSerializer(serializers.ModelSerializer):
    initiator_name = serializers.CharField(source="initiator_persona.name", read_only=True)
    target_name = serializers.CharField(source="target_persona.name", read_only=True)

    class Meta:
        model = SceneActionRequest
        fields = [
            "id",
            "scene",
            "initiator_persona",
            "initiator_name",
            "target_persona",
            "target_name",
            "action_key",
            "action_template",
            "technique",
            "status",
            "difficulty_choice",
            "resolved_difficulty",
            "result_interaction",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "resolved_difficulty",
            "result_interaction",
            "created_at",
            "resolved_at",
        ]


class SceneActionRequestCreateSerializer(serializers.Serializer):
    scene = serializers.IntegerField()
    target_persona = serializers.IntegerField()
    action_key = serializers.CharField(max_length=100)
    difficulty_choice = serializers.CharField(max_length=20, required=False)


class ConsentResponseSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=ConsentDecision.choices)
