"""Serializers for command descriptors."""

from typing import Any

from rest_framework import serializers

from commands.types import CommandDescriptor, Kwargs


class CommandDescriptorSerializer(serializers.Serializer):
    """Serialize :class:`CommandDescriptor` dataclass instances."""

    label = serializers.CharField()
    action = serializers.CharField()
    params = serializers.JSONField(default=dict)
    icon = serializers.CharField(required=False, allow_null=True)

    def create(self, validated_data: Kwargs) -> CommandDescriptor:
        """Create a :class:`CommandDescriptor` from ``validated_data``."""
        return CommandDescriptor(**validated_data)

    def update(
        self,
        instance: CommandDescriptor,
        validated_data: Kwargs,
    ) -> CommandDescriptor:
        """Update ``instance`` with ``validated_data``."""
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        return instance


class CommandSerializer(serializers.Serializer):
    """Serialize commands into payload dictionaries."""

    def to_representation(self, instance: Any) -> dict[str, Any]:
        """Convert a command into a payload via ``to_payload``."""

        return dict(instance.to_payload())
