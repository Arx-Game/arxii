"""Combat-agnostic tempo seam for round/turn gating.

The unified action dispatch layer consults ``get_active_round_context`` to
determine whether a player's action should be declaration-gated (a round is
active) or can proceed immediately. Callers never import ``CombatEncounter``
directly — all combat specifics are hidden behind this resolver.

Usage::

    ctx = get_active_round_context(character_sheet)
    if ctx is not None:
        # A round is active; player must declare, not act immediately.
        if ctx.is_declaration_open:
            ctx.record_declaration(character_sheet, player_action, kwargs)
    else:
        # No active round — dispatch immediately.
        ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RoundContext(ABC):
    """Abstract base for an active game round that gates player actions.

    Concrete subclasses wrap the relevant round/turn model (e.g.
    ``CombatEncounter``) and expose a narrow interface used by the unified
    dispatch layer. The interface deliberately contains no combat vocabulary
    so that non-combat tempo providers (scene turns, etc.) can implement it
    without friction.
    """

    @property
    @abstractmethod
    def round_id(self) -> tuple[int, int]:
        """Stable identifier for the active round.

        Returns a ``(context_id, round_number)`` tuple.  For combat this is
        ``(encounter.pk, encounter.round_number)``.  The tuple must be
        deterministic and comparable — callers use it to de-duplicate entries
        in the bridge table introduced by the next task.
        """
        ...

    @property
    @abstractmethod
    def is_declaration_open(self) -> bool:
        """True when players may still submit declarations for this round.

        For combat: ``True`` iff the encounter's status is ``DECLARING``.
        """
        ...

    @abstractmethod
    def record_declaration(
        self,
        character: Any,
        player_action: Any,
        kwargs: dict[str, Any],
    ) -> None:
        """Record a player's declared action for this round.

        Raises ``NotImplementedError`` until the bridge model is added in
        the next task (P2T8).  Callers should guard with
        ``is_declaration_open`` before calling this.
        """
        ...


def get_active_round_context(character: Any) -> RoundContext | None:
    """Return the active ``RoundContext`` for *character*, or ``None``.

    A non-``None`` return means a round is currently in progress and player
    actions must be declaration-gated rather than dispatched immediately.

    The resolver imports from ``world.combat.round_context`` at call-time to
    keep the top-level ``actions`` package free of combat imports.  Future
    non-combat tempo providers would add a branch here without changing
    callers.

    Args:
        character: The ``CharacterSheet`` instance for the acting character.

    Returns:
        A ``RoundContext`` if the character is currently in an active
        (non-completed) encounter as an ACTIVE participant, else ``None``.
    """
    from world.combat.round_context import resolve_combat_round_context  # noqa: PLC0415

    return resolve_combat_round_context(character)
