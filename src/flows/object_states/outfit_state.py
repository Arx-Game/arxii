"""Object state wrapper for Outfit instances."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from flows.object_states.base_state import BaseState
from flows.object_states.item_state import ItemState

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.items.models import Outfit


class OutfitState(BaseState):
    """Mutable wrapper for an outfit during a flow run.

    Permission methods default to True. Behavior packages plug in via
    ``_run_package_hook`` to deny actions for cursed/locked outfits or
    other reactive scenarios.
    """

    @property
    def outfit(self) -> Outfit:
        """Return the wrapped Outfit, narrowed for type-checkers."""
        return cast("Outfit", self.obj)

    def can_apply(self, actor: BaseState | None = None) -> bool:
        """Whether ``actor`` may apply this outfit."""
        result = self._run_package_hook("can_apply", actor)
        if result is not None:
            return bool(result)
        if actor is None or actor.obj is None:
            return True
        return self.is_reachable_by(actor.obj)

    def is_reachable_by(self, character_obj: ObjectDB) -> bool:
        """Whether ``character_obj`` can apply this outfit.

        Delegates to the wardrobe's reachability — the outfit definition
        lives in the wardrobe, so the wardrobe must be in reach.
        """
        wardrobe_state = ItemState(self.outfit.wardrobe, context=self.context)
        return wardrobe_state.is_reachable_by(character_obj)
