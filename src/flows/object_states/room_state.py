from typing import TYPE_CHECKING, Any

from flows.consts import GLANCE_MODE
from flows.object_states.base_state import BaseState
from world.scenes.models import Scene

if TYPE_CHECKING:
    from flows.scene_data_manager import SceneDataManager
    from typeclasses.rooms import Room


class RoomState(BaseState):
    """
    RoomState represents the state for room objects.
    """

    def __init__(self, obj: "Room", context: "SceneDataManager") -> None:
        """Initialize RoomState with proper Room typing."""
        super().__init__(obj, context)
        # Now mypy knows self.obj is a Room instance
        self.obj: Room

    default_description = "This is a room."

    @property
    def active_scene(self) -> Scene | None:
        """Return the active scene cached on this room."""
        return self.obj.active_scene

    @property
    def appearance_template(self) -> str:
        return "{name}\n{desc}\n{exits}\n{characters}\n{things}"

    @property
    def description(self) -> str:
        try:
            return self.obj.item_data.get_display_description() or self.default_description
        except AttributeError:
            return self.default_description

    def get_display_desc(self, mode: str = "look", **kwargs: Any) -> str:
        """Return the room description.

        Order: season/phase variant (#3291) replaces the base desc, unless an
        event's ``temporary_description`` overlay is active (that always wins;
        see ``world.events.services._apply_room_overlay``); the area-quality
        suffix, if any, is appended last.
        """
        desc = super().get_display_desc(mode=mode, **kwargs)
        if mode == GLANCE_MODE:
            return desc
        from world.areas.cleanup_services import (  # noqa: PLC0415
            area_quality_description_suffix,
        )
        from world.areas.services import get_room_profile  # noqa: PLC0415

        profile = get_room_profile(self.obj)
        if profile is not None:
            overlay_active = bool(self.obj.item_data.temporary_description)
            if not overlay_active:
                from evennia_extensions.services.room_desc_variants import (  # noqa: PLC0415
                    resolve_room_description,
                )
                from world.game_clock.services import get_ic_now  # noqa: PLC0415

                variant_desc = resolve_room_description(profile, get_ic_now())
                if variant_desc is not None:
                    desc = variant_desc
            if profile.area is not None:
                suffix = area_quality_description_suffix(profile.area)
                if suffix:
                    desc = f"{desc}\n\n{suffix}"
        return desc

    def get_categories(self) -> dict:
        # For now, no extra room-specific categories.
        return {}

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    def can_move(
        self,
        actor: "BaseState | None" = None,
        dest: "BaseState | None" = None,
    ) -> bool:
        """Return ``False`` to disallow moving rooms."""

        return False
