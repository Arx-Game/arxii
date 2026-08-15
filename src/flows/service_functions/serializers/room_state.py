"""Serializers for room state and object data."""

from rest_framework import serializers

from flows.object_states.base_state import BaseState
from flows.object_states.exit_state import ExitState
from flows.types import RealmInfo, SerializedObjectState


class ObjectStateSerializer(serializers.Serializer):
    """Serializer for BaseState instances."""

    dbref = serializers.CharField()
    name = serializers.CharField()
    thumbnail_url = serializers.URLField(allow_null=True)
    commands = serializers.ListField(child=serializers.CharField())
    is_mission_board = serializers.BooleanField()

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

        board_target_ids = (self.context or {}).get("board_target_ids") or frozenset()

        return {
            "dbref": instance.obj.dbref,
            "name": instance.get_display_name(looker=looker),
            "thumbnail_url": self._resolve_thumbnail_for_viewer(instance, looker),
            "commands": [key for key in command_keys if key in dispatcher_tags],
            # #3044 — lets the web room-objects panel offer a "View Board"
            # affordance without string-matching object names. A board is a
            # plain examinable Object with an active BOARD-kind MissionGiver
            # pointed at it (no dedicated typeclass — see MissionGiver's
            # docstring), so this can't be derived from typeclass alone.
            "is_mission_board": instance.obj.pk in board_target_ids,
        }

    def _resolve_thumbnail_for_viewer(
        self,
        instance: BaseState,
        looker: BaseState | None,
    ) -> str | None:
        """Re-resolve thumbnail with viewer-aware condition visibility (#2196).

        ``BaseState.__init__`` resolves the thumbnail without knowing who's
        looking. Here, when we have a looker, we re-check hidden conditions
        only if the looker owns the character (sees their own conditions).
        """
        from world.conditions.thumbnail_services import resolve_thumbnail  # noqa: PLC0415

        viewer_can_see_hidden = looker is not None and looker.obj == instance.obj
        return resolve_thumbnail(
            instance.obj,
            persona=instance._resolved_persona,  # noqa: SLF001 — BaseState seam, set in __init__
            viewer_can_see_hidden=viewer_can_see_hidden,
        )

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
    has_unseen_observer = serializers.BooleanField()

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

        from world.scenes.services import has_unseen_observers  # noqa: PLC0415

        return {
            "id": scene_id,
            "name": name,
            "description": description,
            "is_owner": is_owner,
            "has_unseen_observer": has_unseen_observers(instance),
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
    ) -> tuple[
        list[SerializedObjectState],
        list[SerializedObjectState],
        list[SerializedObjectState],
    ]:
        from world.conditions.services import can_perceive  # noqa: PLC0415
        from world.missions.constants import GiverKind  # noqa: PLC0415
        from world.missions.models import MissionGiver  # noqa: PLC0415

        characters = []
        objects = []
        exits = []

        content_states = list(room.contents)
        # #3044 — one batched query for the whole room rather than a
        # MissionGiver lookup per object (no-queries-in-loops).
        content_ids = [state.obj.pk for state in content_states]
        board_target_ids = frozenset(
            MissionGiver.objects.filter(
                giver_kind=GiverKind.BOARD,
                is_active=True,
                target_id__in=content_ids,
            ).values_list("target_id", flat=True)
        )

        for obj in content_states:
            if obj is caller:
                continue

            is_character = self._is_character(obj)
            if is_character and not can_perceive(caller.obj, obj.obj):
                # #1225: a concealed-and-undetected character is imperceptible to
                # this caller — omit entirely rather than merely masking the name.
                continue

            obj_serializer = ObjectStateSerializer(
                obj,
                context={"looker": caller, "board_target_ids": board_target_ids},
            )
            serialized = obj_serializer.data

            if isinstance(obj, ExitState):
                exits.append(serialized)
            elif is_character:
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

    def _get_ancestry(self, room: BaseState) -> list[dict[str, object]]:
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

    def _get_realm(self, room: BaseState) -> RealmInfo | None:
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

    def _is_room_owner(self, caller: BaseState, room: BaseState) -> bool:
        """Whether the caller's ACTIVE persona owns this room (#1470 editor gate).

        Active persona, never primary — gating on primary would leak alt ownership.
        """
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.locations.services import is_owner  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        try:
            sheet = caller.obj.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return False
        return is_owner(active_persona_for_sheet(sheet), room.obj)

    def _is_room_public(self, room: BaseState) -> bool:
        """Whether the room is publicly listed (the editor's privacy toggle state)."""
        from evennia_extensions.models import room_is_publicly_listed  # noqa: PLC0415

        return room_is_publicly_listed(room.obj)

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
        room_data["is_owner"] = self._is_room_owner(caller, room)
        room_data["is_public"] = self._is_room_public(room)

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
            "heat": self._get_heat(caller, room),
            "hub": self._get_hub(room),
            "npc_givers": self._get_npc_givers(room),
            "decorations": self._get_decorations(room),
            "comfort_level": self._get_comfort_level(room),
        }

    def _get_decorations(self, room: BaseState) -> list[str]:
        """#2991 — placed decoration names, oldest first, so decor is legible in scenes.

        Additive: doesn't touch the room's authored ``desc``, and doesn't replace
        the owner build-HUD's richer ``comfort_summary`` breakdown.

        Read-only: ``room_profile_or_none`` (not ``world.areas.services.get_room_profile``,
        which get-or-creates) — this is a payload build on the room-state hot path, not a
        place that should ever write a ``RoomProfile`` row into existence (CI query-count /
        hot-path-write audit, #2991).
        """
        from world.buildings.models import RoomDecoration  # noqa: PLC0415

        try:
            profile = room.obj.room_profile_or_none
        except AttributeError:
            return []
        if profile is None:
            return []
        return list(
            RoomDecoration.objects.filter(room_profile=profile)
            .order_by("placed_at")
            .values_list("kind__name", flat=True)
        )

    def _get_comfort_level(self, room: BaseState) -> int:
        """#2991 — the room's bare 1-10 comfort level (no per-character offset)."""
        from world.locations.services import comfort_level  # noqa: PLC0415

        return comfort_level(room.obj)

    def _get_heat(self, caller: BaseState, room: BaseState) -> dict[str, str] | None:
        """#1765 — the caller's own pursuit tier here (self-only; None when SAFE)."""
        from world.justice.display import room_heat_payload  # noqa: PLC0415

        return room_heat_payload(caller.obj, room.obj)

    def _get_hub(self, room: BaseState) -> dict[str, object] | None:
        """#1450 — the room's civic-hub tidings block (None when no board/crier here).

        Same feed for every viewer: hub tidings are what the LOCAL societies talk
        about (room → area → societies), not viewer-scoped.
        """
        from world.areas.services import get_room_profile  # noqa: PLC0415
        from world.room_features.services import active_hub_feature  # noqa: PLC0415
        from world.tidings.services import hub_feed_for_room  # noqa: PLC0415

        profile = get_room_profile(room.obj)
        feature = active_hub_feature(profile)
        if feature is None:
            return None
        # #1826 — the hub's area anchors the public wanted board; the frontend
        # fetches /api/justice/wanted/?area= itself so this broadcast stays cheap.
        area = profile.area if profile is not None else None
        return {
            "kind": feature.feature_kind.service_strategy,
            "name": feature.feature_kind.name,
            "area_id": area.pk if area is not None else None,
            "items": [
                {
                    "kind": item.kind,
                    "headline": item.headline,
                    "subject": item.subject,
                    "category": item.category,
                    "occurred_at": item.occurred_at.isoformat(),
                }
                for item in hub_feed_for_room(room.obj, limit=10)
            ],
        }

    def _get_npc_givers(self, room: BaseState) -> list[dict[str, object]]:
        """#3044 — active class-1+ NPC placements (Functionary) standing here.

        A ``Functionary`` is the "talk to this NPC" front door
        (``world.npc_services.models.Functionary``): it carries NO ObjectDB of
        its own (a class-1 NPC is a faceless room placement, not a physical
        object), so it can never appear in ``characters``/``objects`` above —
        this is a separate, room-anchored lookup, not a per-occupant flag.
        ``role_id`` is exactly the kwarg the existing
        ``NPCInteractionDialog``/``start_interaction`` seam expects.
        """
        from world.areas.services import get_room_profile  # noqa: PLC0415
        from world.npc_services.models import Functionary  # noqa: PLC0415

        try:
            profile = get_room_profile(room.obj)
        except (AttributeError, TypeError):
            return []
        return [
            {
                "role_id": functionary.role_id,
                "name": functionary.name_override or functionary.role.name,
            }
            for functionary in Functionary.objects.filter(
                room=profile, is_active=True
            ).select_related("role")
        ]


def build_room_state_payload(caller: BaseState, room: BaseState) -> dict[str, object]:
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
