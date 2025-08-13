"""Serializers for room state and object data."""

from typing import Any, Dict, List

from rest_framework import serializers

from flows.object_states.base_state import BaseState
from flows.object_states.exit_state import ExitState


class ObjectStateSerializer(serializers.Serializer):
    """Serializer for BaseState instances."""

    dbref = serializers.IntegerField()
    name = serializers.CharField()
    thumbnail_url = serializers.URLField(allow_null=True)
    commands = serializers.ListField(child=serializers.CharField())

    def to_representation(self, instance):
        """Convert BaseState instance to dict representation."""
        if not isinstance(instance, BaseState):
            raise serializers.ValidationError(
                f"Expected BaseState instance, got {type(instance)}"
            )

        looker = self.context.get("looker") if self.context else None
        command_keys = self._collect_command_keys(looker)

        return {
            "dbref": instance.obj.dbref,
            "name": instance.get_display_name(looker=looker),
            "thumbnail_url": instance.thumbnail_url,
            "commands": [
                key
                for key in command_keys
                if key in getattr(instance, "dispatcher_tags", [])
            ],
        }

    def _collect_command_keys(self, caller: BaseState | None) -> List[str]:
        """Return command keys available to caller."""
        if caller is None:
            return []
        try:
            cmdset = caller.obj.cmdset.current
        except AttributeError:
            return []
        if not cmdset:
            return []
        return [cmd.key for cmd in cmdset.commands]


class SceneDataSerializer(serializers.Serializer):
    """Serializer for scene data."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    is_owner = serializers.BooleanField()

    def to_representation(self, instance):
        """Convert scene data to dict representation."""
        if instance is None:
            return None

        caller = self.context.get("caller")
        if not caller:
            raise serializers.ValidationError(
                "Caller context is required for scene data"
            )

        try:
            is_owner = (
                instance.is_owner(caller.account)
                if hasattr(caller, "account")
                else False
            )
        except AttributeError:
            is_owner = False

        return {
            "id": getattr(instance, "id", None),
            "name": getattr(instance, "name", ""),
            "description": getattr(instance, "description", ""),
            "is_owner": is_owner,
        }


class RoomStatePayloadSerializer(serializers.Serializer):
    """Serializer for room state payload data."""

    room = ObjectStateSerializer()
    objects = ObjectStateSerializer(many=True)
    exits = ObjectStateSerializer(many=True)
    scene = SceneDataSerializer(allow_null=True)

    def to_representation(self, instance):
        """Convert room state data to structured payload."""
        if isinstance(instance, dict):
            # Already serialized data
            return instance

        # Extract caller and room from context or instance
        caller = self.context.get("caller")
        room = self.context.get("room")

        if not caller or not room:
            raise serializers.ValidationError(
                "Both 'caller' and 'room' must be provided in context"
            )

        if not isinstance(caller, BaseState) or not isinstance(room, BaseState):
            raise serializers.ValidationError(
                "Caller and room must be BaseState instances"
            )

        # Serialize room data
        room_serializer = ObjectStateSerializer(room, context={"looker": caller})
        room_data = room_serializer.data

        # Serialize objects and exits
        objects = []
        exits = []

        for obj in room.contents:
            if obj is caller:
                continue

            obj_serializer = ObjectStateSerializer(obj, context={"looker": caller})
            serialized = obj_serializer.data

            if isinstance(obj, ExitState):
                exits.append(serialized)
            else:
                objects.append(serialized)

        # Serialize scene data
        active_scene = getattr(room, "active_scene", None)
        scene_serializer = SceneDataSerializer(active_scene, context={"caller": caller})
        scene_data = scene_serializer.data

        return {
            "room": room_data,
            "objects": objects,
            "exits": exits,
            "scene": scene_data,
        }


def build_room_state_payload(caller: BaseState, room: BaseState) -> Dict[str, Any]:
    """Build a room state payload using Django serializers.

    This replaces the manual dict building in flows.helpers.payloads.

    Args:
        caller: State of the requesting character.
        room: Room state to describe.

    Returns:
        Structured payload describing room, objects, exits, and scene.
    """
    serializer = RoomStatePayloadSerializer(
        None,  # No instance needed, we use context
        context={"caller": caller, "room": room},
    )
    return serializer.to_representation(None)
