"""Serializers for the actions app."""

from __future__ import annotations

from rest_framework import serializers

from actions.constants import ActionTargetType
from actions.models import ActionTemplate


class ActionTemplateSerializer(serializers.ModelSerializer):
    """Read-only serializer for ActionTemplate."""

    requires_target = serializers.SerializerMethodField()

    class Meta:
        model = ActionTemplate
        fields = ["id", "name", "description", "target_type", "requires_target"]

    def get_requires_target(self, obj: ActionTemplate) -> bool:
        return obj.target_type in (
            ActionTargetType.SINGLE,
            ActionTargetType.FILTERED_GROUP,
        )
