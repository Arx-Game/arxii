"""Service layer for the Room Features framework.

- Service strategy registry — each feature's home app registers a handler
  at app-ready time (Sanctum: ``world.magic``).
- ``complete_room_feature_progression`` — the ROOM_FEATURE_PROGRESSION
  ProjectKind handler. Looks up the project's
  :class:`RoomFeatureProgressionDetails`, finds the right strategy via
  the registry, and invokes it with ``(project, target_level,
  outcome_tier)``.
- ``can_modify_room_features`` — permission gate for install/upgrade.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from world.checks.types import CheckOutcome
    from world.projects.models import Project
    from world.scenes.models import Persona


# ---------------------------------------------------------------------------
# Service strategy registry
# ---------------------------------------------------------------------------


# Signature: handler(project, target_level, outcome_tier) -> None
RoomFeatureStrategyHandler = Callable[["Project", int, "CheckOutcome | None"], None]


def _default_strategy_not_registered(
    project: Project, target_level: int, outcome_tier: CheckOutcome | None
) -> None:
    msg = (
        "No room-feature strategy registered yet for this kind. Each kind's "
        "home app must call register_room_feature_strategy() at app-ready time."
    )
    raise NotImplementedError(msg)


ROOM_FEATURE_STRATEGIES: dict[str, RoomFeatureStrategyHandler] = {}

# Snapshot of the default (empty) registry so tests can reset between
# cases — mirrors npc_services.effects.reset_offer_effect_handlers.
_DEFAULT_STRATEGIES: dict[str, RoomFeatureStrategyHandler] = dict(ROOM_FEATURE_STRATEGIES)


def register_room_feature_strategy(strategy_key: str, handler: RoomFeatureStrategyHandler) -> None:
    """Register/override the strategy handler for ``strategy_key``.

    Each feature's home app calls this at app-ready time. Sanctum's
    ``world.magic`` registers ``RoomFeatureServiceStrategy.SANCTUM`` →
    ``world.magic.services.sanctum.handle_progression``.
    """
    ROOM_FEATURE_STRATEGIES[strategy_key] = handler


def reset_room_feature_strategies() -> None:
    """Restore the empty baseline. Test-only escape hatch."""
    ROOM_FEATURE_STRATEGIES.clear()
    ROOM_FEATURE_STRATEGIES.update(_DEFAULT_STRATEGIES)


# ---------------------------------------------------------------------------
# ROOM_FEATURE_PROGRESSION Project handler — wired in apps.py
# ---------------------------------------------------------------------------


def complete_room_feature_progression(
    project: Project, outcome_tier: CheckOutcome | None = None
) -> None:
    """Handle resolution of a ROOM_FEATURE_PROGRESSION project.

    Loads the per-project ``RoomFeatureProgressionDetails`` payload,
    looks up the target ``RoomFeatureKind.service_strategy`` in the
    registry, and dispatches with ``(project, target_level, outcome_tier)``.
    """
    from world.room_features.models import RoomFeatureProgressionDetails  # noqa: PLC0415

    details = (
        RoomFeatureProgressionDetails.objects.select_related("target_feature_kind")
        .filter(project=project)
        .first()
    )
    if details is None:
        msg = (
            f"Project {project.pk} resolved as ROOM_FEATURE_PROGRESSION but has "
            "no RoomFeatureProgressionDetails row."
        )
        raise RuntimeError(msg)

    strategy_key = details.target_feature_kind.service_strategy
    handler = ROOM_FEATURE_STRATEGIES.get(strategy_key)
    if handler is None:
        handler = _default_strategy_not_registered
    handler(project, details.target_level, outcome_tier)


# ---------------------------------------------------------------------------
# Permission gate
# ---------------------------------------------------------------------------


def can_modify_room_features(persona: Persona, room: DefaultObject) -> bool:
    """Standing required to install or upgrade a feature in this room.

    Composes the existing ``world.locations.services`` checks. A persona
    has standing when they own the room (directly or via cascade through
    org membership) OR have an active tenancy. The Plan 4 spec also
    mentions building-manager standing as a third condition, but the
    ``BuildingManager`` model is not yet built (#670-era work) — the
    install/upgrade UI gates only on owner+tenant for now. When
    ``BuildingManager`` lands, extend this gate before broadening UI
    surfaces that rely on it.
    """
    from world.locations.services import is_owner, is_tenant  # noqa: PLC0415

    return is_owner(persona, room) or is_tenant(persona, room)
