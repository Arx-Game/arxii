"""Serializers for command descriptors."""

from rest_framework import serializers

from commands.types import CommandDescriptor


class CommandDescriptorSerializer(serializers.Serializer):
    """Serialize :class:`CommandDescriptor` dataclass instances."""

    label = serializers.CharField()
    action = serializers.CharField()
    params = serializers.JSONField(default=dict)
    icon = serializers.CharField(required=False, allow_null=True)

    def create(self, validated_data):
        """Create a :class:`CommandDescriptor` from ``validated_data``."""
        return CommandDescriptor(**validated_data)

    def update(self, instance: CommandDescriptor, validated_data):
        """Update ``instance`` with ``validated_data``."""
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        return instance
