"""Battle-conclusion hook registry (#1832 Task 7).

``battles`` is the general/reusable system (ADR-0010); specific systems that
attach battle-vehicle state to a persistent object (e.g. ``ships``) register a
hook here instead of ``battles`` importing them directly. Mirrors the
``register_kind_handler`` pattern in ``world/projects/services.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.battles.models import Battle

ConclusionHook = Callable[["Battle"], None]

_HOOKS: list[ConclusionHook] = []


def register_battle_conclusion_hook(hook: ConclusionHook) -> None:
    """Register a callable to run whenever a battle concludes."""
    _HOOKS.append(hook)


def run_battle_conclusion_hooks(battle: Battle) -> None:
    """Invoke every registered conclusion hook with ``battle``."""
    for hook in _HOOKS:
        hook(battle)


def clear_battle_conclusion_hooks() -> None:
    """Test-only: clear the hook registry."""
    _HOOKS.clear()
