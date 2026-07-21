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

from world.room_features.constants import (
    SOCIAL_HUB_CROWD_DRAW_PER_LEVEL,
    SOCIAL_HUB_TRAFFIC_SOURCE,
    RoomFeatureServiceStrategy,
)

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

# The at-ready baseline: registrations made with ``as_default=True`` (every
# ``AppConfig.ready()`` call site) land here too, so ``reset`` restores the
# fully-wired registry — never the empty import-time state (#2490: an
# import-time snapshot let a tearDown reset wipe sanctum's registration for
# the rest of the CI shard process).
_DEFAULT_STRATEGIES: dict[str, RoomFeatureStrategyHandler] = {}


def register_room_feature_strategy(
    strategy_key: str,
    handler: RoomFeatureStrategyHandler,
    *,
    as_default: bool = False,
) -> None:
    """Register/override the strategy handler for ``strategy_key``.

    Each feature's home app calls this at app-ready time with
    ``as_default=True`` so the registration survives test resets. Sanctum's
    ``world.magic`` registers ``RoomFeatureServiceStrategy.SANCTUM`` →
    ``world.magic.services.sanctum.handle_progression``. Tests wiring a mock
    override omit ``as_default`` and pair with
    :func:`reset_room_feature_strategies` in tearDown.
    """
    ROOM_FEATURE_STRATEGIES[strategy_key] = handler
    if as_default:
        _DEFAULT_STRATEGIES[strategy_key] = handler


def reset_room_feature_strategies() -> None:
    """Restore the at-ready baseline registrations. Test-only escape hatch."""
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


def handle_bank_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """BANK strategy (#2540 Layer 4): row-only install.

    The feature's 'content' is reachability — where one stands, the org-vault
    deposit/withdraw actions may be performed. Custody itself lives in
    ``world.items``' ``OrganizationVault``, never in the room.
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


def handle_workshop_of_iniquity_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """WORKSHOP_OF_INIQUITY strategy (#1825): row-only install/level.

    The workshop gates criminal projects (frame jobs now; future counterfeiting /
    heist planning) — the gate is read-time (``frame_jobs._workshop_in_room``), so
    the handler is a plain install/level.
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


def sync_social_hub_traffic(room_profile: RoomProfile) -> None:
    """Reconcile the room's crowd-draw TRAFFIC modifier to its hub's current level.

    Idiomatic crowd draw (#1694): the hub contributes a ``LocationValueModifier``
    on the room's TRAFFIC stat, which flows through the location cascade into
    ``room_activity_band`` — so a busier hub automatically draws bigger crowds AND
    spreads deeds further (more fame from retelling, the spread-path amplification
    Apostate ratified). Reconciled from the *current* active hub, so it is correct
    after install, upgrade, OR dissolve (a future dissolve path need only call
    this): no active hub → value 0 → the cascade row is deleted. Dependency
    direction stays clean — room_features depends on locations, never the reverse.
    """
    from world.locations.constants import StatKey  # noqa: PLC0415
    from world.locations.services import set_room_stat_modifier  # noqa: PLC0415

    instance = active_social_hub_in(room_profile)
    value = instance.level * SOCIAL_HUB_CROWD_DRAW_PER_LEVEL if instance else 0
    set_room_stat_modifier(
        room_profile,
        StatKey.TRAFFIC,
        source=SOCIAL_HUB_TRAFFIC_SOURCE,
        value=value,
    )


def handle_social_hub_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """SOCIAL_HUB strategy (#1694): install/level the feature, mark the hub, draw crowds.

    Beyond the row-only install every other #675 feature does, this:
    - flips the room's ``is_social_hub`` designation on — an amplified hub implies
      a hub; and
    - reconciles the room's crowd-draw TRAFFIC modifier to the new level
      (``sync_social_hub_traffic``), which the deed-spreading path reads via
      ``room_activity_band`` — so higher-level hubs spread deeds further and win
      more fame from the retelling.

    Dissolving the feature does NOT clear ``is_social_hub``: the amplification
    ends (no active instance; ``active_social_hub_in`` returns None and a
    reconcile drops the TRAFFIC modifier) but the baseline gossip-hub
    designation — which staff may also have set independently (#1572) — is
    deliberately left in place rather than risk clobbering a staff-set baseline.
    """
    details = _install_or_level_feature(project, target_level)
    room_profile = details.target_room_profile
    if not room_profile.is_social_hub:
        room_profile.is_social_hub = True
        room_profile.save(update_fields=["is_social_hub"])
    sync_social_hub_traffic(room_profile)


# ---------------------------------------------------------------------------
# ROOM_DEFENSE_INSTALLATION Project handler -- wired in apps.py (#2177)
# ---------------------------------------------------------------------------


def complete_defense_installation(
    project: Project,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """Handle resolution of a ROOM_DEFENSE_INSTALLATION project (#2177).

    Plain three-way branch on defense_kind -- no dict registry, unlike
    ROOM_FEATURE_STRATEGIES, since all three kinds ship in this app and are
    fixed mechanics, not a catalog other apps plug into (Decision 2).
    """
    from world.room_features.constants import DefenseKind  # noqa: PLC0415
    from world.room_features.models import DefenseProgressionDetails  # noqa: PLC0415

    details = (
        DefenseProgressionDetails.objects.select_related(
            "target_exit_profile", "target_room_profile", "resonance"
        )
        .filter(project=project)
        .first()
    )
    if details is None:
        msg = (
            f"Project {project.pk} resolved as ROOM_DEFENSE_INSTALLATION but has "
            "no DefenseProgressionDetails row."
        )
        raise RuntimeError(msg)

    if details.defense_kind == DefenseKind.EXIT_BARS:
        _install_or_level_bars(details.target_exit_profile, details.target_level)
    elif details.defense_kind == DefenseKind.ROOM_WARD:
        _install_or_level_ward(
            details.target_room_profile,
            details.target_level,
            details.resonance,
            reaction_condition=details.reaction_condition,
            reaction_damage_amount=details.reaction_damage_amount or 0,
        )
    else:
        _install_or_level_alarm(details.target_room_profile, details.target_level)


def _install_or_level_bars(exit_profile, target_level: int) -> None:
    from django.utils import timezone as _tz  # noqa: PLC0415

    from world.room_features.models import ExitBarsDetails  # noqa: PLC0415

    details = ExitBarsDetails.objects.filter(exit_profile=exit_profile).active().first()
    if details is None:
        ExitBarsDetails.objects.create(exit_profile=exit_profile, level=max(1, target_level))
        return
    if target_level > details.level:
        details.level = target_level
        details.last_upgraded_at = _tz.now()
        details.save(update_fields=["level", "last_upgraded_at"])


def _install_or_level_ward(
    room_profile: RoomProfile,
    target_level: int,
    resonance,
    *,
    reaction_condition=None,
    reaction_damage_amount: int = 0,
) -> None:
    from django.utils import timezone as _tz  # noqa: PLC0415

    from world.room_features.models import RoomWardDetails  # noqa: PLC0415

    details = RoomWardDetails.objects.filter(room_profile=room_profile).active().first()
    if details is None:
        RoomWardDetails.objects.create(
            room_profile=room_profile,
            level=max(1, target_level),
            resonance=resonance,
            reaction_condition=reaction_condition,
            reaction_damage_amount=reaction_damage_amount,
        )
        return
    update_fields: list[str] = []
    if target_level > details.level:
        details.level = target_level
        details.last_upgraded_at = _tz.now()
        update_fields.extend(["level", "last_upgraded_at"])
    # Update reaction fields if new values were provided on upgrade.
    # A None condition preserves the existing one; a non-None condition
    # replaces it. Damage is always set (0 is a valid "no damage" choice).
    if reaction_condition is not None:
        details.reaction_condition = reaction_condition
        update_fields.append("reaction_condition")
    if reaction_damage_amount:
        details.reaction_damage_amount = reaction_damage_amount
        update_fields.append("reaction_damage_amount")
    if update_fields:
        details.save(update_fields=update_fields)


def _install_or_level_alarm(room_profile: RoomProfile, target_level: int) -> None:
    from django.utils import timezone as _tz  # noqa: PLC0415

    from world.room_features.models import RoomAlarmDetails  # noqa: PLC0415

    details = RoomAlarmDetails.objects.filter(room_profile=room_profile).active().first()
    if details is None:
        RoomAlarmDetails.objects.create(room_profile=room_profile, level=max(1, target_level))
        return
    if target_level > details.level:
        details.level = target_level
        details.last_upgraded_at = _tz.now()
        details.save(update_fields=["level", "last_upgraded_at"])


# ---------------------------------------------------------------------------
# Ward/alarm reaction to unauthorized traversal (#2177)
# ---------------------------------------------------------------------------


def react_to_unauthorized_entry(actor, room) -> None:
    """React to `actor` entering `room` when an active ward/alarm is present
    and the actor lacks owner/tenant standing (#2177).

    Deterministic -- no CheckType roll, mirroring ExitState.can_traverse's
    lock check (Decision 5). Called from
    flows.service_functions.movement.traverse_exit after a successful move.
    """
    from world.locations.services import is_owner, is_tenant  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = actor.character_sheet
    if sheet is None:
        return
    persona = active_persona_for_sheet(sheet)
    if is_owner(persona, room) or is_tenant(persona, room):
        return

    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    room_profile = RoomProfile.objects.filter(objectdb=room).first()
    if room_profile is None:
        return

    _trigger_ward(actor, room_profile)
    _trigger_alarm(actor, room, room_profile)


def _trigger_ward(actor, room_profile: RoomProfile) -> None:
    from world.room_features.models import RoomWardDetails  # noqa: PLC0415

    ward = RoomWardDetails.objects.filter(room_profile=room_profile).active().first()
    if ward is None or ward.lapsed_at is not None:
        return

    if ward.reaction_condition_id is not None:
        from world.conditions.services import apply_condition  # noqa: PLC0415

        apply_condition(
            actor,
            ward.reaction_condition,
            source_description="A ward reacts to your intrusion.",
        )
    if ward.reaction_damage_amount:
        from world.scenes.sudden_harm import arm_or_apply_sudden_harm  # noqa: PLC0415

        arm_or_apply_sudden_harm(
            actor,
            ward.reaction_damage_amount,
            None,
            source_description="A ward lashes out at the intrusion.",
        )


def _trigger_alarm(actor, room, room_profile: RoomProfile) -> None:
    from world.room_features.models import RoomAlarmDetails  # noqa: PLC0415

    alarm = RoomAlarmDetails.objects.filter(room_profile=room_profile).active().first()
    if alarm is None:
        return

    from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
    from flows.service_functions.communication import message_location  # noqa: PLC0415

    sdm = SceneDataManager()
    actor_state = sdm.initialize_state_for_object(actor)
    message_location(actor_state, "An alarm flares to life -- someone has entered uninvited!")

    from world.locations.constants import HolderType  # noqa: PLC0415
    from world.locations.services import current_tenants, effective_owner  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    # Notify every genuine standing-holder able to have installed this alarm in
    # the first place -- can_modify_room_features gates install on
    # is_owner(persona, room) OR is_tenant(persona, room), so notification must
    # reach both an owner-persona (if any) AND active tenant-personas (if any),
    # not just whichever resolves first (#2177 whole-branch review, Important #1:
    # a tenant-only room -- e.g. a StartingArea.grants_residence_tenancy home,
    # with no LocationOwnership row anywhere in the cascade -- was silently
    # dropping this half of the reaction). Org-held ownership/tenancy is a
    # narrower, separately-tested no-op (test_alarm_org_holder_does_not_crash_or_notify)
    # -- fanning out to org membership is a deliberate non-goal here.
    recipient_sheets: dict[int, object] = {}

    ownership = effective_owner(room)
    # LocationOwnership.get_active_target() (inherited from DiscriminatorMixin)
    # resolves the PARENT discriminator (area/room_profile), not the holder --
    # the holder is a second, independent discriminator on this model
    # (holder_type/holder_persona/holder_organization). Read it directly.
    if (
        ownership is not None
        and ownership.holder_type == HolderType.PERSONA
        and ownership.holder_persona is not None
    ):
        sheet = ownership.holder_persona.character_sheet
        recipient_sheets[sheet.pk] = sheet

    for tenancy in current_tenants(room):
        if tenancy.tenant_type != HolderType.PERSONA or tenancy.tenant_persona is None:
            continue
        sheet = tenancy.tenant_persona.character_sheet
        recipient_sheets[sheet.pk] = sheet

    if not recipient_sheets:
        return
    send_narrative_message(
        recipients=list(recipient_sheets.values()),
        body=f"Your alarm at {room.db_key} was triggered.",
        category=NarrativeCategory.SYSTEM,
    )


#: Resonance drained per ward level per daily tick (#2177). Built from day
#: one per the "ship upkeep/penalties immediately, never retrofit" ruling.
_WARD_UPKEEP_PER_LEVEL = 5


def room_ward_upkeep_tick() -> None:
    """Drain each active ward's resonance_reserve; lapse it if depleted (#2177).

    Registered as a daily task in world.game_clock.tasks, mirroring
    sanctum.resonance_generation_tick's registration shape. Idempotent for an
    already-lapsed ward (draining further past 0 is a no-op on the field, but
    lapsed_at is only (re-)set, never cleared, here -- clearing happens only
    via FundRoomWardAction).
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.room_features.models import RoomWardDetails  # noqa: PLC0415

    for ward in RoomWardDetails.objects.filter(dissolved_at__isnull=True):
        cost = ward.level * _WARD_UPKEEP_PER_LEVEL
        if ward.resonance_reserve >= cost:
            ward.resonance_reserve -= cost
            ward.save(update_fields=["resonance_reserve"])
        elif ward.lapsed_at is None:
            ward.resonance_reserve = 0
            ward.lapsed_at = timezone.now()
            ward.save(update_fields=["resonance_reserve", "lapsed_at"])
