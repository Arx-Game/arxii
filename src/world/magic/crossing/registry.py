"""Crossing-ceremony handler registry (ADR-0094, #1987).

Mirrors the ``OfferHandler`` registry pattern in ``commands/offer_registry.py``:
handlers register in ``MagicConfig.ready()`` keyed on ``TargetKind``, and
``execute_crossing_ceremonies`` dispatches via the registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from world.magic.models import Thread


@runtime_checkable
class CrossingCeremonyHandler(Protocol):
    """Protocol for a per-``TargetKind`` crossing ceremony handler.

    Each handler is registered against a ``TargetKind`` value and called by
    ``execute_crossing_ceremonies`` when a thread of that kind crosses one or
    more PathStage crossing levels (3, 6, 11, 16, 21) during an imbue.

    Handlers that wrap variant-discovery logic (GIFT, COVENANT_ROLE) call the
    shared ``execute_ceremony_beat`` helper internally; handlers for kinds with
    other specialization shapes (additive, unlock) call it directly with their
    own narrative body.
    """

    target_kind: str

    def execute(self, *, thread: Thread, starting_level: int, new_level: int) -> None:
        """Run the ceremony for any crossings in ``(starting_level, new_level]``.

        Idempotent: a replay of the same range must not duplicate beats.
        """
        ...


_REGISTRY: dict[str, CrossingCeremonyHandler] = {}


def register_crossing_handler(handler: CrossingCeremonyHandler) -> None:
    """Register a crossing ceremony handler for its ``target_kind``.

    A later registration for the same ``target_kind`` replaces an earlier one
    (matches the offer-registry's append-on-conflict-free assumption; we key by
    kind so there is exactly one handler per kind).
    """
    _REGISTRY[handler.target_kind] = handler


def get_crossing_handler(target_kind: str) -> CrossingCeremonyHandler | None:
    """Return the registered handler for ``target_kind``, or ``None``."""
    return _REGISTRY.get(target_kind)


def all_crossing_handlers() -> list[CrossingCeremonyHandler]:
    """Return all registered handlers (for introspection / debugging)."""
    return list(_REGISTRY.values())


def clear_crossing_registry() -> None:
    """Clear the registry (test-only — isolates registration order between tests)."""
    _REGISTRY.clear()
