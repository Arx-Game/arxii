"""Flow CALL_SERVICE_FUNCTION handlers for the castable effect palette (#1584).

Each handler is keyword-only ``def h(*, payload) -> None`` and is referenced by
its dotted path from a seeded FlowDefinition's CALL_SERVICE_FUNCTION step.
"""

from typing import Any

from world.areas.positioning.models import Position
from world.areas.positioning.services import connect_positions, force_move_to_position, position_of
from world.conditions.constants import (
    BLINK_CONDITION_NAME,
    FORCE_FIELD_CONDITION_NAME,
    REFLECT_CONDITION_NAME,
)
from world.conditions.models import ConditionInstance
from world.magic.models.anima import CharacterAnima


def move_position(*, payload: Any) -> None:
    """Relocate payload.target to payload.destination_position_id (force move).

    Uses force_move_to_position which bypasses capability and gate checks but
    requires destination to be in the same room as the objectdb.
    """
    dest = Position.objects.get(pk=payload.destination_position_id)
    force_move_to_position(payload.target, dest)


def create_obstacle(*, payload: Any) -> None:
    """Make the edge between two positions impassable (an obstacle).

    Connects payload.position_a_id and payload.position_b_id with is_passable=False.
    Passes blocks_flight from payload if present (defaults False).
    """
    a = Position.objects.get(pk=payload.position_a_id)
    b = Position.objects.get(pk=payload.position_b_id)
    blocks_flight = getattr(payload, "blocks_flight", False)  # noqa: GETATTR_LITERAL
    connect_positions(a, b, is_passable=False, blocks_flight=blocks_flight)


# ---------------------------------------------------------------------------
# Reactive helpers (DAMAGE_PRE_APPLY interceptors, #1584)
# ---------------------------------------------------------------------------


def _try_spend_reactive(instance: ConditionInstance) -> bool:
    """Spend the template's reactive_anima_cost from the bearer; False if unaffordable.

    Returns True immediately when cost is 0 (free-to-fire condition).
    Does NOT use select_for_update — single-threaded game tick is the expected
    caller; add locking if a concurrent path is introduced.
    """
    cost = instance.condition.reactive_anima_cost
    if cost <= 0:
        return True
    anima = CharacterAnima.objects.filter(character=instance.target).first()
    if anima is None or anima.current < cost:
        return False
    anima.current -= cost
    anima.save(update_fields=["current"])
    return True


def absorb_pool(*, payload: Any) -> None:
    """Drain a force-field buffer to soak incoming damage (DAMAGE_PRE_APPLY).

    Lowest-priority interceptor (priority 10); mutation-only — overflow still
    lands.  Stop-on-cancel is the dispatch layer's job; we only guard the
    already-zeroed case so a prior mutation-only handler doesn't cause a
    negative debit.

    Mechanics:
    - Finds the bearer's oldest active force-field ConditionInstance.
    - Pays reactive_anima_cost (fizzles silently if unaffordable).
    - Reduces payload.amount by min(buffer, amount); decrements absorb_remaining.
    - Deletes the instance when absorb_remaining reaches 0 (buffer spent).
    """
    if payload.amount <= 0:
        return
    instance = (
        ConditionInstance.objects.filter(
            target=payload.target,
            condition__name=FORCE_FIELD_CONDITION_NAME,
            absorb_remaining__gt=0,
            resolved_at__isnull=True,
        )
        .order_by("pk")  # oldest first — pk is monotone; no applied_at on this model
        .first()
    )
    if instance is None or not _try_spend_reactive(instance):
        return
    soaked = min(instance.absorb_remaining, payload.amount)
    payload.amount -= soaked
    instance.absorb_remaining -= soaked
    if instance.absorb_remaining <= 0:
        instance.delete()  # buffer fully consumed; condition expires
    else:
        instance.save(update_fields=["absorb_remaining"])


def reflect_damage(*, payload: Any) -> None:
    """Bounce incoming damage back to the attacker (DAMAGE_PRE_APPLY, priority 20).

    Finds the bearer's oldest active Mirror Ward ConditionInstance, pays
    reactive_anima_cost via ``_try_spend_reactive`` (fizzles silently if
    unaffordable), zeros ``payload.amount``, then applies the recorded amount to
    the attacker using ``bypass_pre_apply=True`` so the bounce never re-emits
    DAMAGE_PRE_APPLY — terminating any reflect↔reflect loop.

    Attacker resolution from ``payload.source.ref``:
    - ``CombatOpponent``  → ``apply_damage_to_opponent``  (primary E2E path)
    - DefaultCharacter objectdb → lookup active CombatParticipant →
      ``apply_damage_to_participant``
    - None / Technique / unresolvable / no active participant → payload zeroed,
      no bounce (no attacker to hit; no crash).
    """
    if payload.amount <= 0:
        return

    instance = (
        ConditionInstance.objects.filter(
            target=payload.target,
            condition__name=REFLECT_CONDITION_NAME,
            resolved_at__isnull=True,
        )
        .order_by("pk")  # oldest first — pk is monotone
        .first()
    )
    if instance is None or not _try_spend_reactive(instance):
        return

    amount = payload.amount
    payload.amount = 0

    ref = payload.source.ref

    # Lazy imports to avoid circular dependency: combat.services already
    # lazy-imports world.magic.services for thread DR.
    from world.combat.models import (  # noqa: PLC0415
        CombatOpponent,
        CombatParticipant,
        ParticipantStatus,
    )
    from world.combat.services import (  # noqa: PLC0415
        apply_damage_to_opponent,
        apply_damage_to_participant,
    )

    if isinstance(ref, CombatOpponent):
        apply_damage_to_opponent(
            ref, amount, bypass_pre_apply=True, damage_type=payload.damage_type
        )
        return

    # PC attacker path — ref must be a DefaultCharacter objectdb.
    try:
        from evennia.objects.objects import DefaultCharacter  # noqa: PLC0415

        is_character = isinstance(ref, DefaultCharacter)
    except ImportError:
        is_character = False

    if is_character:
        participant = CombatParticipant.objects.filter(
            character_sheet__character=ref, status=ParticipantStatus.ACTIVE
        ).first()
        if participant is not None:
            apply_damage_to_participant(
                participant, amount, bypass_pre_apply=True, damage_type=payload.damage_type
            )
    # else: ref is None / Technique / unknown → payload already zeroed, no bounce


def summon_ally(*, payload: Any) -> None:
    """Create an ALLY CombatOpponent in the caster's encounter, OR — when
    ``payload.military`` is set — a BattleUnit in the caster's active Battle
    (#1711, military-grade summons too potent for a skirmish).

    Reads from payload:
    - ``payload.caster``         – caster's character ObjectDB.
    - ``payload.threat_pool_id`` – pk of the ThreatPool to use.
    - ``payload.bond_rounds``    – optional int; sets bond_expires_round on the
                                   skirmish summon. Not applicable to the military
                                   branch (battles have no per-encounter round-bond
                                   concept).
    - ``payload.max_health``     – optional int (default 30); explicit max_health for
                                   manual mode (skips scaling formula → SQLite-safe).
                                   In the military branch, used as the new unit's
                                   ``strength``.
    - ``payload.military``       – optional bool (default False, #1711). When True,
                                   routes to the BattleUnit branch instead of the
                                   skirmish CombatOpponent branch.
    - ``payload.properties``     – optional list[str] (#1794, military branch only);
                                   Property names to attach to the summoned unit.
    - ``payload.capabilities``   – optional dict[str, int] (#1794, military branch
                                   only); CapabilityType name -> authored magnitude.
    - ``payload.quality``        – optional str (#1711, military branch only); a
                                   ``UnitQuality`` value. Defaults to TRAINED.

    Skirmish resolution (military falsy/absent — unchanged from pre-#1711):
    1. Finds the caster's active CombatParticipant; returns early if not in combat.
    2. Creates an ephemeral MOOK CombatOpponent via ``add_opponent`` (reuse — ADR-0016).
    3. Sets allegiance=ALLY, summoned_by=caster sheet, bond_expires_round if provided.
    4. Defensively moves the summon to the caster's Position (no-op when not positioned).

    Military resolution (payload.military is True, #1711):
    1. Finds the caster's active BattleParticipant; returns early if none (mirrors
       the skirmish no-op convention).
    2. Creates a BattleUnit via ``add_unit`` on the participant's side/place, with
       strength from ``max_health``, quality/properties/capabilities from the
       payload (or defaults), summoned_by=caster sheet.
    """
    if getattr(payload, "military", False):  # noqa: GETATTR_LITERAL
        _summon_military_unit(payload=payload)
        return

    # Lazy imports to avoid the combat↔magic circular dependency.
    from world.combat.constants import (  # noqa: PLC0415
        CombatAllegiance,
        OpponentTier,
        ParticipantStatus,
    )
    from world.combat.models import CombatParticipant, ThreatPool  # noqa: PLC0415
    from world.combat.services import add_opponent  # noqa: PLC0415

    participant = (
        CombatParticipant.objects.filter(
            character_sheet__character=payload.caster,
            status=ParticipantStatus.ACTIVE,
        )
        .select_related("encounter", "character_sheet")
        .first()
    )
    if participant is None:
        return  # Caster is not in active combat — nothing to summon into.

    encounter = participant.encounter
    caster_sheet = participant.character_sheet

    threat_pool = ThreatPool.objects.get(pk=payload.threat_pool_id)
    max_health: int = getattr(payload, "max_health", 30)  # noqa: GETATTR_LITERAL
    bond_rounds: int | None = getattr(payload, "bond_rounds", None)  # noqa: GETATTR_LITERAL

    # Reuse the canonical opponent-creation primitive (anti-reinvention, ADR-0016).
    # Passing max_health explicitly → manual mode → no scaling formula → SQLite-safe.
    opp = add_opponent(
        encounter,
        name=f"{caster_sheet.character.db_key}'s Summon",
        tier=OpponentTier.MOOK,
        threat_pool=threat_pool,
        max_health=max_health,
    )

    # Set summon fields (add_opponent does not set these).
    update_fields = ["allegiance", "summoned_by"]
    opp.allegiance = CombatAllegiance.ALLY
    opp.summoned_by = caster_sheet
    if bond_rounds is not None:
        opp.bond_expires_round = encounter.round_number + bond_rounds
        update_fields.append("bond_expires_round")
    opp.save(update_fields=update_fields)

    # Defensively place the summon at the caster's Position (same room guaranteed).
    pos = position_of(payload.caster)
    if pos is not None:
        force_move_to_position(opp.objectdb, pos)


def _summon_military_unit(*, payload: Any) -> None:
    """Military-grade branch of ``summon_ally`` (#1711): create a BattleUnit in the
    caster's active Battle instead of a CombatOpponent.

    No-op (mirrors the skirmish path's convention) if the caster has no ACTIVE
    BattleParticipant.
    """
    from world.battles.constants import BattleParticipantStatus, UnitQuality  # noqa: PLC0415
    from world.battles.models import BattleParticipant  # noqa: PLC0415
    from world.battles.services import add_unit  # noqa: PLC0415
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.mechanics.models import Property  # noqa: PLC0415

    participant = (
        BattleParticipant.objects.filter(
            character_sheet__character=payload.caster,
            status=BattleParticipantStatus.ACTIVE,
        )
        .select_related("battle", "side", "place", "character_sheet")
        .first()
    )
    if participant is None:
        return  # Caster is not an active battle participant — nothing to summon into.

    caster_sheet = participant.character_sheet
    max_health: int = getattr(payload, "max_health", 30)  # noqa: GETATTR_LITERAL
    quality: str = getattr(payload, "quality", UnitQuality.TRAINED)  # noqa: GETATTR_LITERAL
    property_names: list[str] = getattr(payload, "properties", [])  # noqa: GETATTR_LITERAL
    capability_magnitudes: dict[str, int] = getattr(
        payload,
        "capabilities",  # noqa: GETATTR_LITERAL
        {},
    )

    properties = list(Property.objects.filter(name__in=property_names))
    capability_values = [
        (capability, capability_magnitudes[capability.name])
        for capability in CapabilityType.objects.filter(name__in=capability_magnitudes.keys())
    ]

    add_unit(
        battle=participant.battle,
        side=participant.side,
        name=f"{caster_sheet.character.db_key}'s Summon",
        quality=quality,
        strength=max_health,
        place=participant.place,
        summoned_by=caster_sheet,
        properties=properties,
        capability_values=capability_values,
    )


def move_position_on_condition(*, payload: Any, destination_position_id: int) -> None:
    """CONDITION_APPLIED adapter: relocate payload.target to its cast-time destination.

    Reads the destination from payload.instance.cast_destination (set by the cast
    pipeline via position_params, #2019). Falls back to the static
    destination_position_id step param for backward compatibility (the placeholder
    is 0, so this is a no-op when no cast-time destination was set).

    Used by the teleport (Phase Jump, SELF) and telekinesis (Force Grip, ENEMY)
    effect bundles. For SELF conditions payload.target is the caster; for ENEMY
    conditions it is the enemy objectdb.
    """
    from types import SimpleNamespace  # noqa: PLC0415

    # #2019: Prefer the cast-time destination on the instance.
    try:
        instance = payload.instance
    except AttributeError:
        instance = None
    if instance is not None and instance.cast_destination_id is not None:
        destination_pk = instance.cast_destination_id
    elif destination_position_id > 0:
        destination_pk = destination_position_id
    else:
        return  # no destination resolved — no-op

    move_position(
        payload=SimpleNamespace(
            target=payload.target,
            destination_position_id=destination_pk,
        )
    )


def create_obstacle_on_condition(
    *,
    payload: Any,
    position_a_id: int,
    position_b_id: int,
) -> None:
    """CONDITION_APPLIED adapter: seal the edge between two cast-time positions.

    Reads the positions from payload.instance.cast_position_a / cast_position_b
    (set by the cast pipeline via position_params, #2019). Falls back to the
    static step params for backward compatibility.

    Used by the obstacle (Barricade, SELF) effect bundle.
    """
    from types import SimpleNamespace  # noqa: PLC0415

    # #2019: Prefer the cast-time positions on the instance.
    try:
        instance = payload.instance
    except AttributeError:
        instance = None
    if instance is not None and instance.cast_position_a_id is not None:
        pos_a_pk = instance.cast_position_a_id
        pos_b_pk = instance.cast_position_b_id
    elif position_a_id > 0 and position_b_id > 0:
        pos_a_pk = position_a_id
        pos_b_pk = position_b_id
    else:
        return  # no positions resolved — no-op

    create_obstacle(
        payload=SimpleNamespace(
            position_a_id=pos_a_pk,
            position_b_id=pos_b_pk,
        )
    )


def summon_ally_on_condition(
    *, payload: Any, threat_pool_id: int, bond_rounds: int | None = None, max_health: int = 30
) -> None:
    """CONDITION_APPLIED adapter that bridges to ``summon_ally`` (#1584, Task 14a).

    Seeded as the CALL_SERVICE_FUNCTION step of the Summoning condition's reactive
    flow: casting a SELF summon technique applies the Summoning condition, whose
    trigger fires this with the event's ``ConditionAppliedPayload`` plus the static
    ``threat_pool_id`` / ``bond_rounds`` / ``max_health`` params from the flow step.

    ``payload.target`` is the bearer of the condition, which — for a SELF condition —
    is the caster. We repackage it into the bespoke namespace ``summon_ally`` reads.
    """
    from types import SimpleNamespace  # noqa: PLC0415

    summon_ally(
        payload=SimpleNamespace(
            caster=payload.target,
            threat_pool_id=threat_pool_id,
            bond_rounds=bond_rounds,
            max_health=max_health,
        )
    )


def init_absorb_buffer(*, payload: Any, buffer: int) -> None:
    """CONDITION_APPLIED init: seed the force-field instance's absorb buffer.

    Called by the Aegis Field condition's CONDITION_APPLIED reactive trigger.
    Sets ``absorb_remaining`` to *buffer* on the freshly applied instance only
    when the field is still uninitialized (``absorb_remaining is None``), so a
    double-fire (idempotent seed calls) never overwrites an already-seeded value.
    """
    inst = payload.instance
    if inst is not None and inst.absorb_remaining is None:
        inst.absorb_remaining = buffer
        inst.save(update_fields=["absorb_remaining"])


def blink_dodge(*, payload: Any) -> None:
    """Teleport the bearer to an alternate position, fully avoiding incoming damage.

    Highest-priority DAMAGE_PRE_APPLY interceptor (priority 30). When the bearer
    can pay ``reactive_anima_cost`` via ``_try_spend_reactive``:

    - Repositions the bearer to any other ``Position`` in their current room
      (flavor; if no alternate position exists the move is skipped).
    - Sets ``payload.amount = 0`` (full avoidance).

    Fizzles silently when the bearer cannot afford the cost — attack lands unchanged.
    Mutation-only: setting ``payload.amount = 0`` is what stops lower-priority
    interceptors (they guard on ``payload.amount <= 0``) and zeroes the damage; there
    is no CANCEL_EVENT step (an unconditional cancel would fire on the fizzle path too).
    """
    if payload.amount <= 0:
        return

    instance = (
        ConditionInstance.objects.filter(
            target=payload.target,
            condition__name=BLINK_CONDITION_NAME,
            resolved_at__isnull=True,
        )
        .order_by("pk")
        .first()
    )
    if instance is None or not _try_spend_reactive(instance):
        return

    # Cost paid — attempt relocation (flavor; avoidance is the mechanic).
    current = position_of(payload.target)
    if current is not None:
        dest = Position.objects.filter(room=payload.target.location).exclude(pk=current.pk).first()
    else:
        dest = Position.objects.filter(room=payload.target.location).first()

    if dest is not None:
        force_move_to_position(payload.target, dest)

    payload.amount = 0
