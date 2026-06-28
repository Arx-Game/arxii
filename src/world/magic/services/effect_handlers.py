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
    """Create an ALLY CombatOpponent in the caster's encounter (ACTIVE cast-time handler).

    Reads from payload:
    - ``payload.caster``         – caster's character ObjectDB.
    - ``payload.threat_pool_id`` – pk of the ThreatPool to use.
    - ``payload.bond_rounds``    – optional int; sets bond_expires_round on the summon.
    - ``payload.max_health``     – optional int (default 30); explicit max_health for
                                   manual mode (skips scaling formula → SQLite-safe).

    Resolution:
    1. Finds the caster's active CombatParticipant; returns early if not in combat.
    2. Creates an ephemeral MOOK CombatOpponent via ``add_opponent`` (reuse — ADR-0016).
    3. Sets allegiance=ALLY, summoned_by=caster sheet, bond_expires_round if provided.
    4. Defensively moves the summon to the caster's Position (no-op when not positioned).
    """
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


def move_position_on_condition(*, payload: Any, destination_position_id: int) -> None:
    """CONDITION_APPLIED adapter: relocate ``payload.target`` to a seeded destination.

    Bridges the CONDITION_APPLIED payload shape to ``move_position``, which expects
    ``payload.target`` (the objectdb to move) and ``payload.destination_position_id``
    (the target Position pk).

    Used by the teleport (Phase Jump, SELF) and telekinesis (Force Grip, ENEMY) effect
    bundles.  For SELF conditions ``payload.target`` is the caster; for ENEMY conditions
    it is the enemy objectdb.

    Note — ``destination_position_id`` is seeded as a placeholder (0) in the flow step.
    Runtime destination selection (cast-time target picker) is a follow-up; until then
    an unresolved placeholder makes the cast a **no-op** rather than crashing on a
    ``Position(pk=0)`` lookup (the placeholder pk does not exist).
    """
    from types import SimpleNamespace  # noqa: PLC0415

    if destination_position_id <= 0:
        return  # unresolved placeholder destination — no-op until runtime selection ships

    move_position(
        payload=SimpleNamespace(
            target=payload.target,
            destination_position_id=destination_position_id,
        )
    )


def create_obstacle_on_condition(
    *,
    payload: Any,  # noqa: ARG001
    position_a_id: int,
    position_b_id: int,
) -> None:
    """CONDITION_APPLIED adapter: seal the edge between two positions.

    Bridges the CONDITION_APPLIED payload shape to ``create_obstacle``, which
    expects ``payload.position_a_id`` and ``payload.position_b_id`` (the two
    adjacent Position pks to seal).  ``payload.target`` (the caster) is not
    forwarded — ``create_obstacle`` only needs the position IDs.

    Used by the obstacle (Barricade, SELF) effect bundle.

    Note — ``position_a_id`` / ``position_b_id`` are seeded as placeholders (0, 0).
    Runtime position selection is a follow-up; until then an unresolved placeholder
    makes the cast a **no-op** rather than crashing on a ``Position(pk=0)`` lookup.
    """
    from types import SimpleNamespace  # noqa: PLC0415

    if position_a_id <= 0 or position_b_id <= 0:
        return  # unresolved placeholder positions — no-op until runtime selection ships

    create_obstacle(
        payload=SimpleNamespace(
            position_a_id=position_a_id,
            position_b_id=position_b_id,
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
