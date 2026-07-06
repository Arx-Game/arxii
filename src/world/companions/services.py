"""Service functions for the Companion substrate (#672)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone
from evennia.utils.create import create_object

from world.magic.constants import EffectKind, TargetKind
from world.magic.services.pull_effects import get_pull_effects_for_thread

if TYPE_CHECKING:
    from world.battles.models import Battle, BattleSide, BattleVehicle
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter, CombatOpponent, ThreatPool
    from world.companions.models import Companion, CompanionArchetype
    from world.magic.models.gifts import Gift


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


def companion_capacity(character_sheet: CharacterSheet, gift: Gift) -> int:
    """Total Companion Capacity character_sheet has via gift's Thread level.

    Sums tier-0 (passive, always-on) FLAT_BONUS ThreadPullEffect rows whose
    min_thread_level is at or below the thread's current level — mirrors the
    ``row.min_thread_level > thread.level`` skip idiom in world/magic/handlers.py.
    """
    thread = _companion_thread(character_sheet, gift)
    rows = get_pull_effects_for_thread(thread, tier=0, effect_kind=EffectKind.FLAT_BONUS)
    return sum(row.flat_bonus_amount for row in rows if row.min_thread_level <= thread.level)


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
    objectdb is cleared.
    """
    from world.companions.models import Companion  # noqa: PLC0415 — avoid circular import

    if companion.objectdb is not None:
        companion.objectdb.delete()
    companion.released_at = timezone.now()
    companion.objectdb = None
    companion.save(update_fields=["released_at", "objectdb"])
    # objectdb.delete()'s SET_NULL collector runs a bulk QuerySet.update() at the DB
    # level, outside any single instance's .save() path — any other process-cached
    # Companion for this pk would otherwise keep reporting a stale non-null objectdb.
    Companion.flush_instance_cache()


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
    """
    from world.combat.constants import CombatAllegiance  # noqa: PLC0415
    from world.combat.services import add_opponent  # noqa: PLC0415

    archetype = companion.archetype

    opponent = add_opponent(
        encounter,
        name=companion.name,
        tier=archetype.tier,
        threat_pool=threat_pool,
        max_health=archetype.max_health,
        soak_value=archetype.soak_value,
        existing_objectdb=companion.objectdb,
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
    vehicle.unit.strength = archetype.strength
    vehicle.unit.save(update_fields=["strength"])

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
