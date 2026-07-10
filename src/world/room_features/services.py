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

from world.room_features.constants import RoomFeatureServiceStrategy

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from evennia_extensions.models import RoomProfile
    from world.checks.types import CheckOutcome
    from world.projects.models import Project
    from world.room_features.models import RoomFeatureInstance, RoomFeatureProgressionDetails
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


def _install_or_level_feature(project: Project, target_level: int) -> RoomFeatureProgressionDetails:
    """Shared row-only progression: create the instance at L1 or bump its level.

    Returns the project's progression details so kind-specific handlers can hang
    side effects (e.g. the Town Crier's functionary placement) off the target room.
    """
    from django.utils import timezone as _tz  # noqa: PLC0415

    from world.room_features.models import (  # noqa: PLC0415
        RoomFeatureInstance,
        RoomFeatureProgressionDetails,
    )

    details = RoomFeatureProgressionDetails.objects.select_related(
        "target_room_profile", "target_feature_kind"
    ).get(project=project)
    instance = (
        RoomFeatureInstance.objects.filter(
            room_profile=details.target_room_profile,
            feature_kind=details.target_feature_kind,
        )
        .active()
        .first()
    )
    if instance is None:
        RoomFeatureInstance.objects.create(
            room_profile=details.target_room_profile,
            feature_kind=details.target_feature_kind,
            level=max(1, target_level),
        )
        return details
    if target_level > instance.level:
        instance.level = target_level
        instance.last_upgraded_at = _tz.now()
        instance.save(update_fields=["level", "last_upgraded_at"])
    return details


def handle_command_center_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """COMMAND_CENTER strategy (#930): install or level the feature instance.

    Unlike Sanctum (ritual-installed), a Command Center installs through the
    plain ROOM_FEATURE_PROGRESSION project — level 1 creates the instance,
    higher targets bump it. Its 'content' is reachability: the family books
    surface where a Command Center stands.
    """
    _install_or_level_feature(project, target_level)


def handle_notice_board_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """NOTICE_BOARD strategy (#1450): row-only install.

    The board's 'content' is reachability — where one stands, the room carries
    the local tidings slice (arrival echo, ``tidings local``, web hub panel).
    """
    _install_or_level_feature(project, target_level)


def handle_town_crier_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """TOWN_CRIER strategy (#1450): install the row AND place the crier NPC.

    The crier is a Functionary of the seeded "Town Crier" NPCRole, placed
    idempotently in the target room — the visible IC anchor for the same
    local-tidings reader the Notice Board provides.
    """
    from world.npc_services.functionaries import place_functionary  # noqa: PLC0415
    from world.room_features.seeds import ensure_town_crier_role  # noqa: PLC0415

    details = _install_or_level_feature(project, target_level)
    place_functionary(role=ensure_town_crier_role(), room=details.target_room_profile)


def active_hub_feature(room_profile: RoomProfile) -> RoomFeatureInstance | None:
    """The room's active civic-hub feature (Notice Board or Town Crier), or None.

    ``RoomFeatureInstance`` is a OneToOne per room, so a room carries at most one
    hub surface — board XOR crier. Callers gate every hub read on this.
    """
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    return (
        RoomFeatureInstance.objects.filter(
            room_profile=room_profile,
            feature_kind__service_strategy__in=(
                RoomFeatureServiceStrategy.NOTICE_BOARD,
                RoomFeatureServiceStrategy.TOWN_CRIER,
            ),
        )
        .select_related("feature_kind")
        .active()
        .first()
    )


# ---------------------------------------------------------------------------
# #675 feature-kind active-instance helpers — read-time bonus lookups.
# Each mirrors active_hub_feature's shape: filter by service_strategy, .active().
# ---------------------------------------------------------------------------


def active_library_in(room_profile: RoomProfile) -> RoomFeatureInstance | None:
    """The room's active Library feature, or None.

    Consumed at ``CodexTeachingOffer.accept`` to discount the learner's AP
    cost by ``instance.level * LIBRARY_AP_DISCOUNT_PER_LEVEL``.
    """
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    return (
        RoomFeatureInstance.objects.filter(
            room_profile=room_profile,
            feature_kind__service_strategy=RoomFeatureServiceStrategy.LIBRARY,
        )
        .select_related("feature_kind")
        .active()
        .first()
    )


def active_training_room_in(room_profile: RoomProfile) -> RoomFeatureInstance | None:
    """The room's active Training Room feature, or None.

    Consumed at ``learn_technique`` to discount the learner's AP cost by
    ``instance.level * TRAINING_ROOM_AP_DISCOUNT_PER_LEVEL``.
    """
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    return (
        RoomFeatureInstance.objects.filter(
            room_profile=room_profile,
            feature_kind__service_strategy=RoomFeatureServiceStrategy.TRAINING_ROOM,
        )
        .select_related("feature_kind")
        .active()
        .first()
    )


def active_siege_deck_in(room_profile: RoomProfile) -> RoomFeatureInstance | None:
    """The room's active Siege Deck feature, or None.

    Consumed at the battle bridge to add ``instance.level *
    SIEGE_DECK_ARMAMENT_PER_LEVEL`` to the ship's effective armament.
    """
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    return (
        RoomFeatureInstance.objects.filter(
            room_profile=room_profile,
            feature_kind__service_strategy=RoomFeatureServiceStrategy.SIEGE_DECK,
        )
        .select_related("feature_kind")
        .active()
        .first()
    )


def active_captains_quarters_in(room_profile: RoomProfile) -> RoomFeatureInstance | None:
    """The room's active Captain's Quarters feature, or None.

    Reachability-only — no numeric bonus. Consumed by future surfaces that
    gate on "a Captain's Quarters stands here."
    """
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    return (
        RoomFeatureInstance.objects.filter(
            room_profile=room_profile,
            feature_kind__service_strategy=RoomFeatureServiceStrategy.CAPTAINS_QUARTERS,
        )
        .select_related("feature_kind")
        .active()
        .first()
    )


def active_social_hub_in(room_profile: RoomProfile) -> RoomFeatureInstance | None:
    """The room's active Social Hub feature, or None (#1694).

    Consumed at read time by the renown award path (fame/prestige multiplier)
    and the room-traffic substrate (crowd-draw bonus). ``level`` drives every
    magnitude — see the ``SOCIAL_HUB_*`` constants. Returns None once the
    feature is dissolved, so amplification auto-clears without touching
    ``RoomProfile.is_social_hub`` (the baseline designation persists).
    """
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    return (
        RoomFeatureInstance.objects.filter(
            room_profile=room_profile,
            feature_kind__service_strategy=RoomFeatureServiceStrategy.SOCIAL_HUB,
        )
        .select_related("feature_kind")
        .active()
        .first()
    )


def handle_library_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """LIBRARY strategy (#675): row-only install/level.

    The discount is read-time — ``active_library_in(room)`` at codex accept.
    """
    _install_or_level_feature(project, target_level)


def handle_training_room_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """TRAINING_ROOM strategy (#675): row-only install/level.

    The discount is read-time — ``active_training_room_in(room)`` at
    ``learn_technique``.
    """
    _install_or_level_feature(project, target_level)


def handle_siege_deck_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """SIEGE_DECK strategy (#675): row-only install/level.

    The armament bonus is read-time — ``active_siege_deck_in(room)`` at
    the battle bridge.
    """
    _install_or_level_feature(project, target_level)


def handle_captains_quarters_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """CAPTAINS_QUARTERS strategy (#675): row-only install.

    Reachability-only feature (like Command Center). No numeric bonus.
    """
    _install_or_level_feature(project, target_level)


def handle_social_hub_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """SOCIAL_HUB strategy (#1694): install/level the feature AND mark the hub.

    Beyond the row-only install every other #675 feature does, this flips the
    room's ``is_social_hub`` designation on — an amplified hub implies a hub.
    The bonuses (fame/prestige multiplier, crowd draw) are read-time via
    ``active_social_hub_in(room)`` and scale with ``instance.level``.

    Dissolving the feature does NOT clear ``is_social_hub``: the amplification
    ends (no active instance) but the baseline gossip-hub designation — which
    staff may also have set independently (#1572) — is deliberately left in
    place rather than risk clobbering a staff-set baseline.
    """
    details = _install_or_level_feature(project, target_level)
    room_profile = details.target_room_profile
    if not room_profile.is_social_hub:
        room_profile.is_social_hub = True
        room_profile.save(update_fields=["is_social_hub"])
