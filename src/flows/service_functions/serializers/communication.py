"""Serializers for communication and messaging data."""

from typing import Any

from rest_framework import serializers

from flows.object_states.base_state import BaseState


class MessageParticipantSerializer(serializers.Serializer):
    """Serializer for message participants."""

    name = serializers.CharField()
    dbref = serializers.IntegerField()

    def to_representation(self, instance):
        """Convert participant data to dict representation."""
        if isinstance(instance, BaseState):
            return {
                "name": instance.get_display_name(looker=self.context.get("receiver")),
                "dbref": instance.obj.dbref,
            }
        if isinstance(instance, dict):
            return instance
        # Handle other object types with fallback
        try:
            dbref = instance.dbref
        except AttributeError:
            dbref = None
        if dbref is None:
            try:
                dbref = instance.id
            except AttributeError:
                dbref = 0
        return {
            "name": str(instance),
            "dbref": dbref,
        }


class MessageContentSerializer(serializers.Serializer):
    """Serializer for message content with template substitution."""

    template = serializers.CharField()
    variables = serializers.DictField()

    def to_representation(self, instance):
        """Convert message template and variables to rendered content."""
        if isinstance(instance, dict):
            template = instance.get("template", "")
            variables = instance.get("variables", {})
        else:
            template = str(instance)
            variables = {}

        # Resolve variable references for display names
        receiver = self.context.get("receiver")
        resolved_vars = {}

        for key, obj in variables.items():
            if isinstance(obj, BaseState):
                resolved_vars[key] = obj.get_display_name(looker=receiver)
            else:
                resolved_vars[key] = str(obj)

        return {
            "template": template,
            "variables": resolved_vars,
            "rendered": self._render_template(template, resolved_vars),
        }

    def _render_template(self, template: str, variables: dict[str, Any]) -> str:
        """Render template with variable substitution."""
        try:
            # Simple variable substitution - enhance with proper templating
            result = template
            for key, value in variables.items():
                result = result.replace(f"{{{key}}}", str(value))
            return result
        except Exception:  # noqa: BLE001
            return template


class ChatMessageSerializer(serializers.Serializer):
    """Serializer for chat messages sent to players."""

    sender = MessageParticipantSerializer()
    content = MessageContentSerializer()
    message_type = serializers.CharField()
    timestamp = serializers.DateTimeField(format="iso-8601", read_only=True)

    def to_representation(self, instance):
        """Convert chat message data to structured format."""
        # Extract context
        receiver = self.context.get("receiver")

        # Handle different input formats
        if isinstance(instance, dict):
            sender_data = instance.get("sender")
            content_data = instance.get("content")
            message_type = instance.get("message_type", "chat")
            timestamp = instance.get("timestamp")
        else:
            # Assume instance has attributes
            try:
                sender_data = instance.sender
            except AttributeError:
                sender_data = None
            try:
                content_data = instance.content
            except AttributeError:
                content_data = str(instance)
            try:
                message_type = instance.message_type
            except AttributeError:
                message_type = "chat"
            try:
                timestamp = instance.timestamp
            except AttributeError:
                timestamp = None

        # Serialize components
        sender_serializer = MessageParticipantSerializer(
            sender_data,
            context={"receiver": receiver},
        )
        content_serializer = MessageContentSerializer(
            content_data,
            context={"receiver": receiver},
        )

        return {
            "sender": sender_serializer.data,
            "content": content_serializer.data,
            "message_type": message_type,
            "timestamp": timestamp,
        }


class LocationMessageSerializer(serializers.Serializer):
    """Serializer for messages sent to locations/rooms."""

    participants = MessageParticipantSerializer(many=True)
    content = MessageContentSerializer()
    message_type = serializers.CharField()
    exclude_senders = serializers.BooleanField(default=False)

    def to_representation(self, instance):
        """Convert location message data to structured format."""
        receiver = self.context.get("receiver")

        if isinstance(instance, dict):
            participants = instance.get("participants", [])
            content_data = instance.get("content")
            message_type = instance.get("message_type", "location")
            exclude_senders = instance.get("exclude_senders", False)
        else:
            try:
                participants = instance.participants
            except AttributeError:
                participants = []
            try:
                content_data = instance.content
            except AttributeError:
                content_data = str(instance)
            try:
                message_type = instance.message_type
            except AttributeError:
                message_type = "location"
            try:
                exclude_senders = instance.exclude_senders
            except AttributeError:
                exclude_senders = False

        participants_serializer = MessageParticipantSerializer(
            participants,
            many=True,
            context={"receiver": receiver},
        )
        content_serializer = MessageContentSerializer(
            content_data,
            context={"receiver": receiver},
        )

        return {
            "participants": participants_serializer.data,
            "content": content_serializer.data,
            "message_type": message_type,
            "exclude_senders": exclude_senders,
        }
