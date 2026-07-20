"""Service functions for the Companion substrate (#672)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone
from evennia.utils.create import create_object

from world.magic.constants import EffectKind, TargetKind
from world.magic.services.pull_effects import get_pull_effects_for_thread

if TYPE_CHECKING:
    from world.battles.models import Battle, BattleSide, BattleVehicle
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckOutcome
    from world.combat.models import CombatEncounter, CombatOpponent, ThreatPool
    from world.companions.models import Companion, CompanionArchetype
    from world.magic.models.gifts import Gift
    from world.projects.models import Project


class NoCompanionThreadError(Exception):
    """Raised when the character has no active GIFT thread for the granting gift."""


def _companion_thread(character_sheet: CharacterSheet, gift: Gift):
    from world.magic.models.threads import Thread  # noqa: PLC0415 — avoid circular import

    thread = Thread.objects.filter(
        owner=character_sheet,
        target_kind=TargetKind.GIFT,
        target_gift=gift,
        retired_at__isnull=True,
    ).first()
    if thread is None:
        msg = f"{character_sheet} has no active thread for gift {gift}."
        raise NoCompanionThreadError(msg)
    return thread


def stables_capacity_bonus_for_sheet(character_sheet: CharacterSheet) -> int:
    """Flat Companion Capacity bonus from all Stables the sheet has standing in.

    Derive-on-read: queries active Stables RoomFeatureInstances on rooms
    where the sheet's primary persona is owner or tenant, sums
    ``StablesDetails.capacity_bonus_per_level * instance.level`` across all
    matches. Returns 0 if the character has no Stables or no primary persona.
    """
    from world.companions.models import StablesDetails  # noqa: PLC0415
    from world.locations.services import is_owner, is_tenant  # noqa: PLC0415
    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        persona: Persona = active_persona_for_sheet(character_sheet)
    except Persona.DoesNotExist:
        return 0

    instances = (
        RoomFeatureInstance.objects.active()
        .select_related("feature_kind", "room_profile", "stables_details")
        .filter(feature_kind__service_strategy=RoomFeatureServiceStrategy.STABLES)
    )
    total = 0
    for instance in instances:
        room = instance.room_profile.objectdb
        if room is None:
            continue
        if is_owner(persona, room) or is_tenant(persona, room):
            try:
                details = instance.stables_details
            except StablesDetails.DoesNotExist:
                continue
            total += details.capacity_bonus_per_level * instance.level
    return total


def companion_capacity(character_sheet: CharacterSheet, gift: Gift) -> int:
    """Total Companion Capacity character_sheet has via gift's Thread level.

    Sums tier-0 (passive, always-on) FLAT_BONUS ThreadPullEffect rows whose
    min_thread_level is at or below the thread's current level — mirrors the
    ``row.min_thread_level > thread.level`` skip idiom in world/magic/handlers.py.
    Adds a flat Stables capacity bonus (#1863).
    """
    thread = _companion_thread(character_sheet, gift)
    rows = get_pull_effects_for_thread(thread, tier=0, effect_kind=EffectKind.FLAT_BONUS)
    base = sum(row.flat_bonus_amount for row in rows if row.min_thread_level <= thread.level)
    return base + stables_capacity_bonus_for_sheet(character_sheet)


def used_companion_capacity(character_sheet: CharacterSheet, gift: Gift) -> int:
    """Companion Capacity currently consumed by character_sheet's active companions via gift."""
    from world.companions.models import Companion  # noqa: PLC0415 — avoid circular import

    active = Companion.objects.filter(
        owner=character_sheet,
        granting_gift=gift,
        released_at__isnull=True,
    ).select_related("archetype")
    return sum(c.archetype.capacity_cost for c in active)


def bind_companion(
    *,
    owner: CharacterSheet,
    archetype: CompanionArchetype,
    granting_gift: Gift,
    name: str,
) -> Companion:
    """Create a bonded Companion + its live CompanionObject in owner's current room.

    The caller (the Bind Action, Task 8) is responsible for the capacity
    check and the perform_check roll before calling this — this function has
    no prerequisite logic of its own, mirroring the service-function/Action
    split used throughout src/actions/.
    """
    from typeclasses.companions import CompanionObject  # noqa: PLC0415 — avoid circular import
    from world.companions.models import Companion  # noqa: PLC0415 — avoid circular import

    room = owner.character.location
    companion_object = create_object(CompanionObject, key=name, location=room, nohome=True)
    return Companion.objects.create(
        owner=owner,
        archetype=archetype,
        granting_gift=granting_gift,
        name=name,
        objectdb=companion_object,
    )


def release_companion(companion: Companion) -> None:
    """Release a bonded companion: destroy its live object, keep the row.

    The Companion row is never hard-deleted — released_at is set and
    objectdb is cleared. If the companion was ridden, the rider is
    force-dismounted first (#1843) — a released companion can't keep a rider.
    """
    from world.companions.models import Companion  # noqa: PLC0415 — avoid circular import

    if companion.ridden_by_id is not None:
        dismount_companion(companion.ridden_by)

    if companion.objectdb is not None:
        companion.objectdb.delete()
    companion.released_at = timezone.now()
    companion.objectdb = None
    companion.save(update_fields=["released_at", "objectdb"])
    # objectdb.delete()'s SET_NULL collector runs a bulk QuerySet.update() at the DB
    # level, outside any single instance's .save() path — any other process-cached
    # Companion for this pk would otherwise keep reporting a stale non-null objectdb.
    Companion.flush_instance_cache()


class MountError(Exception):
    """Raised when a mount/dismount attempt is invalid (#1843)."""

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(message)
        self.user_message = user_message or message


def mount_companion(sheet: CharacterSheet, companion: Companion) -> Companion:
    """Mount *sheet* on *companion* — applies the Mounted condition to the rider.

    Validates: the companion's archetype is ridable (``is_mount``), the
    companion belongs to *sheet* and is active/present, and *sheet* is not
    already riding another mount. No mechanical check is rolled — mounting is
    a free declarative action, gated purely on ownership + state.

    Raises:
        MountError: If any validation fails.
    """
    from world.companions.models import Companion  # noqa: PLC0415 — avoid circular import
    from world.companions.mount_content import MOUNTED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    if companion.owner_id != sheet.pk:
        msg = f"{companion.name} is not your companion."
        raise MountError(msg, msg)
    if not companion.is_active:
        msg = f"{companion.name} is no longer active."
        raise MountError(msg, msg)
    if not companion.archetype.is_mount:
        msg = f"{companion.name} cannot be ridden."
        raise MountError(msg, msg)
    if companion.objectdb is None:
        msg = f"{companion.name} has no in-world presence to mount."
        raise MountError(msg, msg)
    if companion.ridden_by_id is not None:
        msg = f"{companion.name} is already being ridden."
        raise MountError(msg, msg)
    if Companion.objects.filter(ridden_by=sheet).exists():
        msg = "You are already mounted on another companion."
        raise MountError(msg, msg)

    companion.ridden_by = sheet
    companion.save(update_fields=["ridden_by"])

    mounted_template = ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)
    apply_condition(sheet.character, mounted_template)
    return companion


def dismount_companion(sheet: CharacterSheet) -> Companion:
    """Dismount *sheet* from whichever companion it is currently riding.

    Removes the Mounted condition from the rider. Called for voluntary
    dismounts, encounter exit (``LeaveEncounterAction``), and companion
    defeat (``release_companion``).

    Raises:
        MountError: If *sheet* is not currently mounted.
    """
    from world.companions.models import Companion  # noqa: PLC0415 — avoid circular import
    from world.companions.mount_content import MOUNTED_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import remove_condition  # noqa: PLC0415

    companion = Companion.objects.filter(ridden_by=sheet).first()
    if companion is None:
        msg = "You are not mounted."
        raise MountError(msg, msg)

    companion.ridden_by = None
    companion.save(update_fields=["ridden_by"])

    mounted_template = ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)
    remove_condition(sheet.character, mounted_template)
    return companion


def materialize_companion_as_combat_opponent(
    companion: Companion,
    encounter: CombatEncounter,
    *,
    threat_pool: ThreatPool | None = None,
) -> CombatOpponent:
    """Bridge a persistent Companion into a duel-scale CombatOpponent (#1873).

    Mirrors ``summon_ally``'s ``add_opponent`` call, but sources stats from
    the persistent ``CompanionArchetype`` instead of a one-shot summon payload.
    Sets allegiance=ALLY, summoned_by=owner, bond_expires_round=None
    (persistent, not ephemeral).

    Args:
        companion: The persistent Companion to bridge.
        encounter: The active CombatEncounter to add the opponent to.
        threat_pool: Optional ThreatPool; if None, uses encounter's first.

    Returns:
        The created CombatOpponent (ALLY, sourced from archetype stats).

    Position defaults to the owner's current position (#2005): a companion
    fights at its owner's side unless placed otherwise. ``owner`` is a
    CharacterSheet; ``owner.character`` is the ObjectDB OneToOne. Unplaced
    owners (or unpositioned rooms) leave the companion unplaced too.
    """
    from world.areas.positioning.services import position_of  # noqa: PLC0415
    from world.combat.constants import CombatAllegiance  # noqa: PLC0415
    from world.combat.services import add_opponent  # noqa: PLC0415

    archetype = companion.archetype
    owner_position = position_of(companion.owner.character)

    opponent = add_opponent(
        encounter,
        name=companion.name,
        tier=archetype.tier,
        threat_pool=threat_pool,
        max_health=archetype.max_health,
        soak_value=archetype.soak_value,
        existing_objectdb=companion.objectdb,
        position=owner_position,
    )

    opponent.allegiance = CombatAllegiance.ALLY
    opponent.summoned_by = companion.owner
    # bond_expires_round stays None — persistent companion, not ephemeral.
    opponent.save(update_fields=["allegiance", "summoned_by"])

    return opponent


def materialize_companion_as_battle_vehicle(
    companion: Companion,
    battle: Battle,
    side: BattleSide,
) -> BattleVehicle:
    """Bridge a persistent Companion into a battle-scale BattleVehicle (#1873).

    Mirrors ``materialize_ship_as_battle_vehicle``, snapshots the archetype's
    strength into a non-structural COMPANION-kind BattleVehicle, and links
    via ``CompanionDeployment`` (mirroring ``ShipDeployment``).

    Args:
        companion: The persistent Companion to bridge.
        battle: The active Battle.
        side: The BattleSide the companion fights on.

    Returns:
        The created BattleVehicle (COMPANION kind, non-structural).
    """
    from world.battles.constants import VehicleKind  # noqa: PLC0415
    from world.battles.services import create_battle_vehicle  # noqa: PLC0415
    from world.companions.models import CompanionDeployment  # noqa: PLC0415

    archetype = companion.archetype
    vehicle = create_battle_vehicle(
        battle=battle,
        side=side,
        place_name=companion.name,
        vehicle_kind=VehicleKind.COMPANION,
        is_structural=False,
    )
    # Set the unit's strength from the archetype (create_battle_vehicle
    # uses the default 100; the companion's strength is authored).
    vehicle.unit.military_unit.strength = archetype.strength
    vehicle.unit.military_unit.save(update_fields=["strength"])

    CompanionDeployment.objects.create(
        companion=companion,
        battle=battle,
        vehicle=vehicle,
    )

    return vehicle


def resolve_companion_defeat(companion: Companion, risk_level: str) -> bool:
    """Resolve a bridged companion's defeat consequence (#1873).

    At LOW/MODERATE/HIGH: no effect on the persistent Companion (ephemeral
    combat participation). At EXTREME/LETHAL: draws from the companion-defeat
    ConsequencePool; the ``die`` outcome calls ``release_companion``.

    Args:
        companion: The persistent Companion whose bridged opponent was defeated.
        risk_level: The RiskLevel of the encounter/battle the companion fought in.

    Returns:
        True if the companion was released (died), False otherwise.
    """
    from world.combat.constants import (  # noqa: PLC0415
        RISK_LEVELS_REQUIRING_ACKNOWLEDGEMENT,
    )

    if risk_level not in RISK_LEVELS_REQUIRING_ACKNOWLEDGEMENT:
        return False

    # Lethal stakes: consult the companion-defeat pool.
    from world.companions.factories_combat import (  # noqa: PLC0415
        create_companion_defeat_pool,
    )

    pool = create_companion_defeat_pool()
    consequences = pool.cached_consequences
    if not consequences:
        return False

    # Weighted draw — mirrors the weighted selection in select_consequence
    # but without a check roll (the defeat IS the trigger, not a check result).
    import random  # noqa: PLC0415

    total_weight = sum(c.weight for c in consequences)
    if total_weight <= 0:
        return False

    roll = random.randint(1, total_weight)  # noqa: S311
    cumulative = 0
    for consequence in consequences:
        cumulative += consequence.weight
        if roll <= cumulative:
            if consequence.character_loss:
                release_companion(companion)
                return True
            return False

    return False


class PromoteSummonError(Exception):
    """Raised when a summon/combatant cannot be promoted to a Companion (#2502)."""

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(message)
        self.user_message = user_message or message


def _is_charmed_by_caster(opponent, caster_character) -> bool:
    """Check if opponent's objectdb has an active Charmed condition sourced by caster.

    Uses get_active_conditions + ConditionInstance.source_character FK check —
    NOT just condition-name presence (which would let any charmer acquire
    another charmer's target).
    """
    from world.conditions.constants import CHARM_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import get_active_conditions  # noqa: PLC0415

    if opponent.objectdb_id is None:
        return False
    charm_template = ConditionTemplate.objects.filter(name=CHARM_CONDITION_NAME).first()
    if charm_template is None:
        return False
    active = get_active_conditions(opponent.objectdb, condition=charm_template)
    return any(inst.source_character_id == caster_character.pk for inst in active)


@transaction.atomic
def promote_summon_to_companion(
    *,
    caster_sheet: CharacterSheet,
    combat_opponent: CombatOpponent,
    archetype: CompanionArchetype,
    granting_gift: Gift,
    name: str,
) -> Companion:
    """Promote an ephemeral summon or charmed enemy into a persistent Companion (#2502).

    Two validation paths:
    - Summon path: combat_opponent.summoned_by == caster_sheet AND
      allegiance == ALLY AND status == ACTIVE.
    - Charmed-enemy path: combat_opponent.objectdb has an active Charmed
      condition whose source_character is the caster's character. Stored
      allegiance stays ENEMY for charmed foes (derived-on-read via
      derive_allegiance).

    On the charmed-enemy path, bind_difficulty is reduced by
    archetype.charm_difficulty_reduction, and the charm condition is consumed
    on successful bind.

    Does NOT transfer the CombatOpponent.objectdb — bind_companion creates a
    fresh CompanionObject (the summon's objectdb is a CombatNPC typeclass,
    wrong for companion behavior). Does NOT remove the CombatOpponent row;
    encounter cleanup handles that.

    Args:
        caster_sheet: The promoting character's sheet.
        combat_opponent: The summon or charmed enemy to promote.
        archetype: The CompanionArchetype to bind as.
        granting_gift: The Gift whose Thread capacity pool is charged.
        name: The companion's name.

    Returns:
        The newly created Companion.

    Raises:
        PromoteSummonError: If the opponent is not a valid promotion target,
            capacity is exceeded, or the bind check fails.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.combat.constants import CombatAllegiance, OpponentStatus  # noqa: PLC0415
    from world.companions.content import BIND_ATTEMPT_CHECK_NAME  # noqa: PLC0415
    from world.conditions.constants import CHARM_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import remove_condition  # noqa: PLC0415

    caster_character = caster_sheet.character

    # --- Validate promotion target (two paths) ---
    is_summon = (
        combat_opponent.summoned_by_id == caster_sheet.pk
        and combat_opponent.allegiance == CombatAllegiance.ALLY
        and combat_opponent.status == OpponentStatus.ACTIVE
    )
    is_charmed_enemy = (
        not is_summon
        and combat_opponent.status == OpponentStatus.ACTIVE
        and _is_charmed_by_caster(combat_opponent, caster_character)
    )
    if not is_summon and not is_charmed_enemy:
        msg = "That target cannot be promoted to a companion."
        raise PromoteSummonError(msg, msg)

    # --- Validate Companion Capacity ---
    capacity = companion_capacity(caster_sheet, granting_gift)
    used = used_companion_capacity(caster_sheet, granting_gift)
    if used + archetype.capacity_cost > capacity:
        msg = "You don't have enough Companion Capacity for another companion."
        raise PromoteSummonError(msg, msg)

    # --- Determine bind difficulty (charm modifier on charmed-enemy path) ---
    bind_difficulty = archetype.bind_difficulty
    charm_applied = is_charmed_enemy and archetype.charm_difficulty_reduction > 0
    if charm_applied:
        bind_difficulty = max(0, bind_difficulty - archetype.charm_difficulty_reduction)

    # --- Roll the bind check ---
    check_type = CheckType.objects.get(name=BIND_ATTEMPT_CHECK_NAME)
    result = perform_check(caster_character, check_type, target_difficulty=bind_difficulty)
    if result.outcome is None or result.outcome.success_level < 0:
        msg = f"The {archetype.name} resists your attempt to bind it."
        raise PromoteSummonError(msg, msg)

    # --- Bind (creates fresh CompanionObject) ---
    companion = bind_companion(
        owner=caster_sheet,
        archetype=archetype,
        granting_gift=granting_gift,
        name=name,
    )

    # --- Consume charm on the charmed-enemy path ---
    if charm_applied and combat_opponent.objectdb is not None:
        charm_template = ConditionTemplate.get_by_name(CHARM_CONDITION_NAME)
        if charm_template is not None:
            remove_condition(combat_opponent.objectdb, charm_template)

    return companion


class CompanionOrderError(Exception):
    """Raised when a companion order is invalid (#1921)."""

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(message)
        self.user_message = user_message or message


def order_companion(  # noqa: C901, PLR0912, PLR0913, PLR0915
    *,
    companion: Companion,
    order_kind: str,
    round_number: int,
    encounter: CombatEncounter | None = None,
    battle: Battle | None = None,
    target_opponent=None,
    target_unit=None,
    ability=None,
    defending_participant=None,
    target_ally=None,
):
    """Validate and upsert a CompanionOrder directive (#1921).

    Branches by scale (encounter = duel, battle = battle-scale).
    Validates that the companion is deployed in the target context
    and that targets are valid.

    Args:
        companion: The persistent Companion being ordered.
        order_kind: A CompanionOrderKind value.
        round_number: The current round number.
        encounter: The CombatEncounter (duel-scale).
        battle: The Battle (battle-scale).
        target_opponent: The CombatOpponent to attack (duel ATTACK_TARGET).
        target_unit: The BattleUnit to attack (battle ATTACK_TARGET).
        ability: Optional CompanionAbility to use instead of auto-select.
        defending_participant: The CombatParticipant to defend (duel DEFEND_ALLY).
        target_ally: The BattleParticipant to defend (battle DEFEND_ALLY).

    Returns:
        The created or updated CompanionOrder.

    Raises:
        CompanionOrderError: If the order is invalid (wrong owner, not deployed,
            invalid target, etc.).
    """
    from world.combat.constants import CombatAllegiance, OpponentStatus  # noqa: PLC0415
    from world.combat.models import CombatOpponent  # noqa: PLC0415
    from world.companions.constants import CompanionOrderKind  # noqa: PLC0415
    from world.companions.models import CompanionOrder  # noqa: PLC0415

    if ability is not None and ability.archetype_id != companion.archetype_id:
        msg = f"{companion.name} does not have the ability {ability.name}."
        raise CompanionOrderError(msg, msg)

    # --- Duel-scale ---
    if encounter is not None and battle is None:
        try:
            CombatOpponent.objects.get(
                summoned_by=companion.owner,
                encounter=encounter,
                status=OpponentStatus.ACTIVE,
            )
        except CombatOpponent.DoesNotExist:
            msg = f"{companion.name} is not deployed in this encounter."
            raise CompanionOrderError(msg, msg) from None

        if order_kind == CompanionOrderKind.ATTACK_TARGET:
            if target_opponent is None:
                msg = "ATTACK_TARGET requires a target."
                raise CompanionOrderError(msg, msg)
            if target_opponent.encounter_id != encounter.pk:
                msg = "Target is not in this encounter."
                raise CompanionOrderError(msg, msg)
            if target_opponent.allegiance != CombatAllegiance.ENEMY:
                msg = "Target is not an enemy."
                raise CompanionOrderError(msg, msg)
            if target_opponent.status != OpponentStatus.ACTIVE:
                msg = "Target is no longer active."
                raise CompanionOrderError(msg, msg)

        elif order_kind == CompanionOrderKind.DEFEND_ALLY:
            if defending_participant is None:
                msg = "DEFEND_ALLY requires an ally to defend."
                raise CompanionOrderError(msg, msg)
            if defending_participant.encounter_id != encounter.pk:
                msg = "Ally is not in this encounter."
                raise CompanionOrderError(msg, msg)

        order, _ = CompanionOrder.objects.update_or_create(
            companion=companion,
            encounter=encounter,
            round_number=round_number,
            defaults={
                "order_kind": order_kind,
                "ability": ability,
                "target_opponent": target_opponent,
                "defending_participant": defending_participant,
                "battle": None,
                "target_unit": None,
                "target_ally": None,
            },
        )
        return order

    # --- Battle-scale ---
    if battle is not None and encounter is None:
        from world.companions.models import CompanionDeployment  # noqa: PLC0415

        try:
            CompanionDeployment.objects.get(companion=companion, battle=battle)
        except CompanionDeployment.DoesNotExist:
            msg = f"{companion.name} is not deployed in this battle."
            raise CompanionOrderError(msg, msg) from None

        if order_kind == CompanionOrderKind.ATTACK_TARGET:
            if target_unit is None:
                msg = "ATTACK_TARGET requires a target unit."
                raise CompanionOrderError(msg, msg)
            if target_unit.battle_id != battle.pk:
                msg = "Target unit is not in this battle."
                raise CompanionOrderError(msg, msg)

        order, _ = CompanionOrder.objects.update_or_create(
            companion=companion,
            battle=battle,
            round_number=round_number,
            defaults={
                "order_kind": order_kind,
                "ability": ability,
                "target_unit": target_unit,
                "target_ally": target_ally,
                "encounter": None,
                "target_opponent": None,
                "defending_participant": None,
            },
        )
        return order

    msg = "order_companion requires either an encounter or a battle (not both)."
    raise CompanionOrderError(msg, msg)


def handle_stables_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """STABLES strategy: row-only install/level + create StablesDetails (#1863).

    Mirrors handle_town_crier_progression's capture-then-side-effect shape:
    ``_install_or_level_feature`` returns the progression details, which we
    use to resolve the RoomFeatureInstance for the StablesDetails sidecar.
    """
    from world.companions.models import StablesDetails  # noqa: PLC0415
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415
    from world.room_features.services import _install_or_level_feature  # noqa: PLC0415

    details = _install_or_level_feature(project, target_level)
    instance = RoomFeatureInstance.objects.get(
        room_profile=details.target_room_profile,
    )
    StablesDetails.objects.get_or_create(feature_instance=instance)
