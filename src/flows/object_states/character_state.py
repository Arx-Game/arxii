from flows.object_states.base_state import BaseState


class CharacterState(BaseState):
    """
    CharacterState represents the state for character objects.
    """

    @property
    def template(self) -> str:
        # Character-specific template.
        return "Character: {name}\n{description}"

    def get_categories(self) -> dict:
        # For now, no extra character-specific categories.
        return {}
