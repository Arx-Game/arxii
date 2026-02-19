"""Serializers for room state and object data."""

from typing import Any

from rest_framework import serializers

from flows.object_states.base_state import BaseState
from flows.object_states.exit_state import ExitState


class ObjectStateSerializer(serializers.Serializer):
    """Serializer for BaseState instances."""

    dbref = serializers.CharField()
    name = serializers.CharField()
    thumbnail_url = serializers.URLField(allow_null=True)
    commands = serializers.ListField(child=serializers.CharField())

    def to_representation(self, instance):
        """Convert BaseState instance to dict representation."""
        if not isinstance(instance, BaseState):
            msg = f"Expected BaseState instance, got {type(instance)}"
            raise serializers.ValidationError(
                msg,
            )

        looker = self.context.get("looker") if self.context else None
        command_keys = self._collect_command_keys(looker)
        try:
            dispatcher_tags = instance.dispatcher_tags
        except AttributeError:
            dispatcher_tags = []

        return {
            "dbref": instance.obj.dbref,
            "name": instance.get_display_name(looker=looker),
            "thumbnail_url": instance.thumbnail_url,
            "commands": [key for key in command_keys if key in dispatcher_tags],
        }

    def _collect_command_keys(self, caller: BaseState | None) -> list[str]:
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

        # If instance has no valid ID, treat as no scene
        try:
            scene_id = instance.id
        except AttributeError:
            scene_id = None
        if scene_id is None:
            return None

        caller = self.context.get("caller")
        if not caller:
            msg = "Caller context is required for scene data"
            raise serializers.ValidationError(
                msg,
            )

        try:
            account = caller.account
        except AttributeError:
            account = None
        if account is None:
            is_owner = False
        else:
            try:
                is_owner = instance.is_owner(account)
            except AttributeError:
                is_owner = False

        try:
            name = instance.name
        except AttributeError:
            name = ""
        try:
            description = instance.description
        except AttributeError:
            description = ""

        return {
            "id": scene_id,
            "name": name,
            "description": description,
            "is_owner": is_owner,
        }


class RoomStatePayloadSerializer(serializers.Serializer):
    """Serializer for room state payload data."""

    room = ObjectStateSerializer()
    characters = ObjectStateSerializer(many=True)
    objects = ObjectStateSerializer(many=True)
    exits = ObjectStateSerializer(many=True)
    scene = SceneDataSerializer(allow_null=True)

    def _get_context_states(self) -> tuple[BaseState, BaseState]:
        caller = self.context.get("caller")
        room = self.context.get("room")

        if not caller or not room:
            msg = "Both 'caller' and 'room' must be provided in context"
            raise serializers.ValidationError(
                msg,
            )

        if not isinstance(caller, BaseState) or not isinstance(room, BaseState):
            msg = "Caller and room must be BaseState instances"
            raise serializers.ValidationError(
                msg,
            )

        return caller, room

    def _is_character(self, state: BaseState) -> bool:
        """Return True if the state wraps a puppeted object (has active sessions)."""
        try:
            return bool(state.obj.sessions.all())
        except AttributeError:
            return False

    def _serialize_contents(
        self,
        room: BaseState,
        caller: BaseState,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        characters = []
        objects = []
        exits = []

        for obj in room.contents:
            if obj is caller:
                continue

            obj_serializer = ObjectStateSerializer(obj, context={"looker": caller})
            serialized = obj_serializer.data

            if isinstance(obj, ExitState):
                exits.append(serialized)
            elif self._is_character(obj):
                characters.append(serialized)
            else:
                objects.append(serialized)

        return characters, objects, exits

    def _get_active_scene(self, room: BaseState):
        try:
            active_scene = room.active_scene
        except AttributeError:
            active_scene = None
        if active_scene is None:
            return None
        try:
            active_scene_id = active_scene.id
        except AttributeError:
            active_scene_id = None
        if active_scene_id is None:
            return None
        return active_scene

    def _get_ancestry(self, room: BaseState) -> list[dict]:
        """Get area ancestry breadcrumbs for a room."""
        try:
            from world.areas.services import get_room_profile  # noqa: PLC0415

            profile = get_room_profile(room.obj)
        except (AttributeError, TypeError):
            return []
        if not profile.area:
            return []
        from world.areas.serializers import AreaBreadcrumbSerializer  # noqa: PLC0415
        from world.areas.services import get_ancestry  # noqa: PLC0415

        ancestry = get_ancestry(profile.area)
        return AreaBreadcrumbSerializer(ancestry, many=True).data

    def _get_realm(self, room: BaseState) -> dict | None:
        """Get effective realm for a room."""
        try:
            from world.areas.services import get_room_profile  # noqa: PLC0415

            profile = get_room_profile(room.obj)
        except (AttributeError, TypeError):
            return None
        if not profile.area:
            return None
        from world.areas.services import get_effective_realm  # noqa: PLC0415

        realm = get_effective_realm(profile.area)
        if realm is None:
            return None
        return {
            "id": realm.pk,
            "name": realm.name,
            "theme": realm.theme,
        }

    def to_representation(self, instance):
        """Convert room state data to structured payload."""
        if isinstance(instance, dict):
            # Already serialized data
            return instance

        caller, room = self._get_context_states()

        # Serialize room data
        room_serializer = ObjectStateSerializer(room, context={"looker": caller})
        room_data = room_serializer.data
        room_data["description"] = room.description
        room_data["ancestry"] = self._get_ancestry(room)
        room_data["realm"] = self._get_realm(room)

        # Serialize characters, objects, and exits
        characters, objects, exits = self._serialize_contents(room, caller)

        # Serialize scene data
        active_scene = self._get_active_scene(room)
        scene_serializer = SceneDataSerializer(active_scene, context={"caller": caller})
        scene_data = scene_serializer.to_representation(active_scene)

        return {
            "room": room_data,
            "characters": characters,
            "objects": objects,
            "exits": exits,
            "scene": scene_data,
        }


def build_room_state_payload(caller: BaseState, room: BaseState) -> dict[str, Any]:
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
    return serializer.to_representation(None)  # type: ignore[no-any-return]
