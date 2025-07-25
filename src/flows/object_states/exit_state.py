from flows.object_states.base_state import BaseState


class ExitState(BaseState):
    """State wrapper for exit objects."""

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    def can_move(
        self,
        actor: "BaseState | None" = None,
        dest: "BaseState | None" = None,
    ) -> bool:
        """Return ``False`` to prevent moving exits."""

        return False

    def can_traverse(self, actor: "BaseState | None" = None) -> bool:
        """Return ``True`` if ``actor`` may traverse this exit.

        Args:
            actor: State attempting the action.

        Returns:
            bool: Always ``True``.
        """

        return True
