"""Object state wrapper for item instances."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from flows.object_states.base_state import BaseState

if TYPE_CHECKING:
    from world.items.models import ItemInstance


class ItemState(BaseState):
    """Mutable wrapper for an item during a flow run.

    Permission methods default to True. Behavior packages plug in via
    ``_run_package_hook`` to deny actions for cursed, soulbound, or
    locked items without changing the service surface.
    """

    @property
    def instance(self) -> ItemInstance:
        """Return the wrapped ItemInstance, narrowed for type-checkers."""
        return cast("ItemInstance", self.obj)

    def can_take(self, taker: BaseState | None = None) -> bool:
        """Whether ``taker`` may pick up this item."""
        result = self._run_package_hook("can_take", taker)
        if result is not None:
            return bool(result)
        return True

    def can_drop(self, dropper: BaseState | None = None) -> bool:
        """Whether ``dropper`` may drop this item."""
        result = self._run_package_hook("can_drop", dropper)
        if result is not None:
            return bool(result)
        return True

    def can_give(
        self,
        giver: BaseState | None = None,
        recipient: BaseState | None = None,
    ) -> bool:
        """Whether ``giver`` may give this item to ``recipient``."""
        result = self._run_package_hook("can_give", giver, recipient)
        if result is not None:
            return bool(result)
        return True

    def can_equip(self, wearer: BaseState | None = None) -> bool:
        """Whether ``wearer`` may equip this item."""
        result = self._run_package_hook("can_equip", wearer)
        if result is not None:
            return bool(result)
        return True
