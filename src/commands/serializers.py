"""Serializers for command descriptors."""

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from rest_framework import serializers

from commands.types import CommandDescriptor, Kwargs


class CommandDescriptorSerializer(serializers.Serializer[CommandDescriptor]):
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


class SupportsCommandPayload(Protocol):
    """Protocol for objects that can serialize to command payloads."""

    def to_payload(self) -> Mapping[str, Any] | Iterable[tuple[str, Any]]:
        """Return data representing the command payload."""


class CommandSerializer(serializers.BaseSerializer[SupportsCommandPayload]):
    """Serialize commands into payload dictionaries."""

    def to_representation(self, instance: SupportsCommandPayload) -> Any:
        """Convert a command into a payload via ``to_payload``."""

        return dict(instance.to_payload())
