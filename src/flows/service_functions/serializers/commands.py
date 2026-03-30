"""Serializers for command data structures."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers
from rest_framework_dataclasses.serializers import DataclassSerializer

from commands.descriptors import CommandDescriptor, DispatcherDescriptor


class DispatcherDescriptorSerializer(DataclassSerializer):
    """Serializer for DispatcherDescriptor instances."""

    class Meta:
        dataclass = DispatcherDescriptor


class CommandDescriptorSerializer(DataclassSerializer):
    """Serializer for CommandDescriptor instances."""

    class Meta:
        dataclass = CommandDescriptor
        exclude = ["descriptors"]


class CommandSerializer(serializers.Serializer):
    """Serializer for command instances.

    Delegates to the command's ``to_payload()`` method, which builds
    the descriptor from action metadata (for action-based commands) or
    from usage declarations (for FrontendMetadataMixin commands).
    """

    def to_representation(self, instance: Any) -> dict[str, Any]:
        """Serialize a command by calling its to_payload() method."""
        if not hasattr(instance, "to_payload"):
            msg = f"Command {type(instance)} does not implement to_payload()"
            raise serializers.ValidationError(msg)
        return instance.to_payload()
