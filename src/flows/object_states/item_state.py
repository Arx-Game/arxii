"""Object state wrapper for item instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flows.object_states.base_state import BaseState

if TYPE_CHECKING:
    from flows.object_states.character_state import CharacterState


class ItemState(BaseState):
    """Mutable wrapper for an item during a flow run.

    Permission methods default to True. Triggers and behaviors plug in
    via the reactive layer to deny actions for cursed, soulbound, or
    locked items without changing the service surface.
    """

    def can_take(self, taker: CharacterState) -> bool:
        """Whether ``taker`` may pick up this item."""
        return True

    def can_drop(self, dropper: CharacterState) -> bool:
        """Whether ``dropper`` may drop this item."""
        return True

    def can_give(
        self,
        giver: CharacterState,
        recipient: CharacterState,
    ) -> bool:
        """Whether ``giver`` may give this item to ``recipient``."""
        return True

    def can_equip(self, wearer: CharacterState) -> bool:
        """Whether ``wearer`` may equip this item."""
        return True
