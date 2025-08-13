"""Serializers for command data structures."""

from rest_framework import serializers

from commands.descriptors import CommandDescriptor, DispatcherDescriptor


class DispatcherDescriptorSerializer(serializers.Serializer):
    """Serializer for DispatcherDescriptor instances."""

    syntax = serializers.CharField()
    context = serializers.CharField()

    def to_representation(self, instance):
        """Convert DispatcherDescriptor to dict representation."""
        if isinstance(instance, DispatcherDescriptor):
            return {
                "syntax": instance.syntax,
                "context": instance.context,
            }
        elif isinstance(instance, dict):
            return instance
        else:
            raise serializers.ValidationError(
                f"Expected DispatcherDescriptor or dict, got {type(instance)}"
            )


class CommandDescriptorSerializer(serializers.Serializer):
    """Serializer for CommandDescriptor instances."""

    key = serializers.CharField()
    aliases = serializers.ListField(child=serializers.CharField())
    dispatchers = DispatcherDescriptorSerializer(many=True)

    def to_representation(self, instance):
        """Convert CommandDescriptor to dict representation."""
        if isinstance(instance, CommandDescriptor):
            return {
                "key": instance.key,
                "aliases": instance.aliases,
                "dispatchers": DispatcherDescriptorSerializer(
                    instance.dispatchers, many=True
                ).data,
            }
        elif isinstance(instance, dict):
            return instance
        else:
            raise serializers.ValidationError(
                f"Expected CommandDescriptor or dict, got {type(instance)}"
            )


class CommandSerializer(serializers.Serializer):
    """Serializer for ArxCommand instances, replacing command.to_payload()."""

    context = serializers.CharField(required=False, allow_null=True)

    def to_representation(self, instance):
        """Convert ArxCommand instance to dict representation."""
        from commands.command import ArxCommand

        if not isinstance(instance, ArxCommand):
            raise serializers.ValidationError(
                f"Expected ArxCommand instance, got {type(instance)}"
            )

        context = self.context.get("context") if hasattr(self, "context") else None

        dispatcher_descs = []
        for dispatcher in instance.dispatchers:
            try:
                dispatcher.bind(instance)
                disp_context = self._get_dispatcher_context(dispatcher)

                if context and disp_context != context:
                    continue

                dispatcher_desc = DispatcherDescriptor(
                    syntax=dispatcher.get_syntax_string(), context=disp_context
                )
                dispatcher_descs.append(dispatcher_desc)
            except Exception as e:
                # Log the error but don't break the entire serialization
                # This handles cases where older commands might have issues
                import logging

                logging.warning(
                    f"Failed to serialize dispatcher for command "
                    f"{instance.key}: {e}"
                )
                continue

        descriptor = CommandDescriptor(
            key=instance.key,
            aliases=sorted(instance.aliases) if instance.aliases else [],
            dispatchers=dispatcher_descs,
        )

        return CommandDescriptorSerializer(descriptor).data

    @staticmethod
    def _get_dispatcher_context(dispatcher) -> str:
        """Get a context label for a dispatcher."""
        from commands.dispatchers import TargetDispatcher, TargetTextDispatcher

        if isinstance(dispatcher, (TargetDispatcher, TargetTextDispatcher)):
            return "object"
        return "room"
