"""Serializers for command data structures."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from commands.descriptors import CommandDescriptor, DispatcherDescriptor


class DispatcherDescriptorSerializer(serializers.Serializer):
    """Serializer for DispatcherDescriptor instances."""

    syntax = serializers.CharField()
    context = serializers.CharField()

    def to_representation(self, instance: DispatcherDescriptor | dict[str, Any]) -> dict[str, str]:
        """Convert DispatcherDescriptor to dict representation."""
        if isinstance(instance, DispatcherDescriptor):
            return {
                "syntax": instance.syntax,
                "context": instance.context,
            }
        if isinstance(instance, dict):
            return instance
        msg = f"Expected DispatcherDescriptor or dict, got {type(instance)}"
        raise serializers.ValidationError(msg)


class CommandDescriptorSerializer(serializers.Serializer):
    """Serializer for CommandDescriptor instances."""

    key = serializers.CharField()
    aliases = serializers.ListField(child=serializers.CharField())
    dispatchers = DispatcherDescriptorSerializer(many=True)

    def to_representation(self, instance: CommandDescriptor | dict[str, Any]) -> dict[str, Any]:
        """Convert CommandDescriptor to dict representation."""
        if isinstance(instance, CommandDescriptor):
            return {
                "key": instance.key,
                "aliases": instance.aliases,
                "dispatchers": DispatcherDescriptorSerializer(
                    instance.dispatchers,
                    many=True,
                ).data,
            }
        if isinstance(instance, dict):
            return instance
        msg = f"Expected CommandDescriptor or dict, got {type(instance)}"
        raise serializers.ValidationError(msg)


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
