"""Crafting handler registry: maps CraftingRecipeKind → CraftingHandler instances.

Pattern mirrors ``world.room_features.services.ROOM_FEATURE_STRATEGIES``:
a module-level dict + ``register`` / ``get_handler`` functions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.crafting.constants import CraftingRecipeKind

if TYPE_CHECKING:
    from world.items.crafting.handlers import CraftingHandler


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_HANDLER_REGISTRY: dict[str, CraftingHandler] = {}


def register(kind: CraftingRecipeKind, handler: CraftingHandler) -> None:
    """Register *handler* for *kind*.

    Called at module import time by ``handlers.py``.  Subsequent calls with
    the same ``kind`` overwrite the previous entry (test-reset pattern).
    """
    _HANDLER_REGISTRY[kind.value] = handler


def get_handler(kind: CraftingRecipeKind) -> CraftingHandler:
    """Return the registered handler for *kind*.

    Raises:
        KeyError: No handler has been registered for this kind.
    """
    try:
        return _HANDLER_REGISTRY[kind.value]
    except KeyError:
        msg = f"No crafting handler registered for kind {kind!r}."
        raise KeyError(msg) from None


def reset_registry() -> None:
    """Clear all registered handlers. Test-only escape hatch."""
    _HANDLER_REGISTRY.clear()
