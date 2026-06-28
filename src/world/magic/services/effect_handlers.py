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


def blink_dodge(*, payload: Any) -> None:
    """Teleport the bearer to an alternate position, fully avoiding incoming damage.

    Highest-priority DAMAGE_PRE_APPLY interceptor (priority 30). When the bearer
    can pay ``reactive_anima_cost`` via ``_try_spend_reactive``:

    - Repositions the bearer to any other ``Position`` in their current room
      (flavor; if no alternate position exists the move is skipped).
    - Sets ``payload.amount = 0`` (full avoidance).

    Fizzles silently when the bearer cannot afford the cost — attack lands unchanged.
    The CANCEL_EVENT flow step (Task 14) stops lower-priority handlers; this
    handler only zeros the payload.
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
