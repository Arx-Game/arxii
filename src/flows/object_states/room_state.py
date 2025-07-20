from flows.object_states.base_state import BaseState


class RoomState(BaseState):
    """
    RoomState represents the state for room objects.
    """

    @property
    def template(self) -> str:
        # Room-specific template.
        return "Room: {name}\n{description}"

    def get_categories(self) -> dict:
        # For now, no extra room-specific categories.
        return {}
