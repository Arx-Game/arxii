"""Object state wrapper for item instances."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from flows.object_states.base_state import BaseState

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.items.models import ItemInstance


class ItemState(BaseState):
    """Mutable wrapper for an item during a flow run.

    Permission methods enforce reach (can the actor physically interact with
    this item, including walking the container chain?) and possession (is the
    actor actually carrying this item?). Behavior packages plug in via
    ``_run_package_hook`` to deny actions for cursed, soulbound, or locked
    items without changing the service surface.
    """

    @property
    def instance(self) -> ItemInstance:
        """Return the wrapped ItemInstance, narrowed for type-checkers."""
        return cast("ItemInstance", self.obj)

    # ------------------------------------------------------------------
    # Reachability + possession helpers
    # ------------------------------------------------------------------

    def is_in_possession(self, character_obj: ObjectDB) -> bool:
        """Whether ``character_obj`` is carrying this item (directly or in their inventory).

        Walks the ``contained_in`` chain. The topmost (uncontained) item must be
        located on ``character_obj``. Container open-state is not relevant here —
        closed containers in your own inventory still count as possession.
        """
        item = self.instance
        while item.contained_in is not None:
            item = item.contained_in
        return item.game_object is not None and item.game_object.location == character_obj

    def is_reachable_by(self, character_obj: ObjectDB) -> bool:
        """Whether ``character_obj`` can physically interact with this item.

        Walks the ``contained_in`` chain. Any closed container in the chain blocks
        reach. The topmost item must be either on ``character_obj`` (carried) or in
        ``character_obj.location`` (the same room).
        """
        item = self.instance
        while item.contained_in is not None:
            container = item.contained_in
            if container.template.supports_open_close and not container.is_open:
                return False
            item = container
        if item.game_object is None:
            return False
        obj_location = item.game_object.location
        return obj_location in (character_obj, character_obj.location)

    # ------------------------------------------------------------------
    # Permission checks
    # ------------------------------------------------------------------

    def can_take(self, taker: BaseState | None = None) -> bool:
        """Whether ``taker`` may pick up this item."""
        result = self._run_package_hook("can_take", taker)
        if result is not None:
            return bool(result)
        if taker is None or taker.obj is None:
            return True  # no concrete actor — default permissive (used by tests / package hooks)
        return self.is_reachable_by(taker.obj)

    def can_drop(self, dropper: BaseState | None = None) -> bool:
        """Whether ``dropper`` may drop this item."""
        result = self._run_package_hook("can_drop", dropper)
        if result is not None:
            return bool(result)
        if dropper is None or dropper.obj is None:
            return True  # no concrete actor — default permissive (used by tests / package hooks)
        return self.is_in_possession(dropper.obj)

    def can_give(
        self,
        giver: BaseState | None = None,
        recipient: BaseState | None = None,
    ) -> bool:
        """Whether ``giver`` may give this item to ``recipient``."""
        result = self._run_package_hook("can_give", giver, recipient)
        if result is not None:
            return bool(result)
        if giver is None or giver.obj is None:
            return True  # no concrete actor — default permissive (used by tests / package hooks)
        return self.is_in_possession(giver.obj)

    def can_equip(self, wearer: BaseState | None = None) -> bool:
        """Whether ``wearer`` may equip this item."""
        result = self._run_package_hook("can_equip", wearer)
        if result is not None:
            return bool(result)
        if wearer is None or wearer.obj is None:
            return True  # no concrete actor — default permissive (used by tests / package hooks)
        return self.is_in_possession(wearer.obj)
