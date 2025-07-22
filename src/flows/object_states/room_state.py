from flows.object_states.base_state import BaseState


class RoomState(BaseState):
    """
    RoomState represents the state for room objects.
    """

    default_description = "This is a room."

    @property
    def appearance_template(self) -> str:
        return "{name}\n" "{desc}\n" "{exits}\n" "{characters}\n" "{things}"

    @property
    def description(self) -> str:
        try:
            return self.obj.item_data.desc or self.default_description
        except AttributeError:
            return self.default_description

    def get_categories(self) -> dict:
        # For now, no extra room-specific categories.
        return {}
