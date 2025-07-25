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

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    def can_move(
        self,
        actor: "BaseState | None" = None,
        dest: "BaseState | None" = None,
    ) -> bool:
        """Return True only if ``actor`` is moving themselves to ``dest``."""

        if actor is not self:
            return False
        return super().can_move(actor=actor, dest=dest)
