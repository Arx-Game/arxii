"""Sneak-stance services (#3288) — mundane stealth over the #1225 Concealed condition.

Ruling (ADR-pending, #3288): stealth conceals IDENTITY, never PRESENCE. A sneaking
character drops off IC surfaces (occupants/look/who — the built #1225 behavior), but
every room they occupy discloses an identity-free unseen presence (room_state flag +
arrival echo), and disclosure is one-way: arrivals always announce, departures are
silent. The concealment roll is checked once per room per visit — on declaration for
the current room, and on each arrival while the stance holds — never re-rollable in
place (spam-until-success is the failure mode that kills).

Callers: ``SneakAction``/``UnsneakAction`` (``actions/definitions/stealth.py``),
``Character.announce_move_from``/``announce_move_to`` (arrival re-roll + silent
departure), and ``check_guard_detection`` (the guard contest strips the stance on a
win). Only sneak-sourced concealment (``source_description == SNEAK_SOURCE``) is ever
re-rolled or stripped here — magical concealment is not this module's to touch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.types import CheckResult
    from world.conditions.models import ConditionInstance, ConditionTemplate

#: PLACEHOLDER base difficulty for slipping into (or arriving hidden in) a room.
#: Deliberately below GUARD_DETECTION_DIFFICULTY (50) — hiding from a room is
#: easier than beating a posted guard. Tuning is a later content pass.
SNEAK_BASE_DIFFICULTY = 25

#: The source_description stamped on sneak-applied Concealed instances; the
#: discriminator that keeps this module's strips/re-rolls off magical concealment.
SNEAK_SOURCE = "sneaking"

#: The #1225 concealment primitive this stance rides (seeded by the
#: perception_conditions cluster, which names stealth as a planned producer).
CONCEALED_TEMPLATE_NAME = "Concealed"


def concealed_template() -> ConditionTemplate | None:
    """The seeded Concealed ConditionTemplate, or None when unseeded."""
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415

    return ConditionTemplate.objects.filter(name=CONCEALED_TEMPLATE_NAME).first()


def sneak_instance(character: ObjectDB) -> ConditionInstance | None:  # noqa: OBJECTDB_PARAM
    """The character's active sneak-sourced Concealed instance, or None."""
    return character.condition_instances.filter(
        condition__name=CONCEALED_TEMPLATE_NAME,
        source_description=SNEAK_SOURCE,
        is_suppressed=False,
        resolved_at__isnull=True,
    ).first()


def is_sneaking(character: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """Whether the character currently holds sneak-sourced concealment."""
    return sneak_instance(character) is not None


def roll_sneak(character: ObjectDB) -> CheckResult:  # noqa: OBJECTDB_PARAM
    """One concealment roll — the SNEAK security oracle vs the base difficulty.

    Raises ValueError when the Stealth CheckType is unseeded (callers surface a
    soft failure).
    """
    from world.checks.constants import SecurityCheckKind  # noqa: PLC0415
    from world.checks.security_services import resolve_security_check  # noqa: PLC0415

    return resolve_security_check(
        SecurityCheckKind.SNEAK,
        character,
        target_difficulty=SNEAK_BASE_DIFFICULTY,
    )


def mark_room_rolled(character: ObjectDB) -> None:  # noqa: OBJECTDB_PARAM
    """Stamp the per-room anti-spam token: one sneak roll per room per visit.

    Transient by design (mirrors ``.ndb.active_travel_token``): a reload clears
    it, which errs on allowing a fresh attempt rather than denying one.
    """
    location = character.location
    character.ndb.sneak_rolled_room_pk = location.pk if location is not None else None


def room_already_rolled(character: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """Whether this room's one sneak roll has already happened this visit."""
    location = character.location
    return location is not None and character.ndb.sneak_rolled_room_pk == location.pk


def start_sneaking(character: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """Apply sneak-sourced concealment after a passed roll. Returns success."""
    from world.conditions.services import apply_condition  # noqa: PLC0415

    template = concealed_template()
    if template is None:
        return False
    result = apply_condition(
        target=character,
        condition=template,
        source_description=SNEAK_SOURCE,
    )
    return result.success


def stop_sneaking(character: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """Remove sneak-sourced concealment (unsneak / guard strip / failed arrival).

    Instance-scoped: resolves only the sneak-sourced instance so a magical
    concealment held at the same time is untouched. Returns True when a stance
    was actually removed.
    """
    from world.conditions.services import remove_condition  # noqa: PLC0415

    instance = sneak_instance(character)
    if instance is None:
        return False
    remove_condition(character, instance.condition)
    return True


def refresh_room_state(character: ObjectDB) -> None:  # noqa: OBJECTDB_PARAM
    """Re-broadcast room_state at the character's location.

    Concealment flips (sneak, unsneak, guard strip, failed arrival re-roll) change
    both the occupant list and the ``has_unseen_presence`` flag; the natural
    receive/leave broadcasts fire before the arrival re-roll resolves, so state
    flips re-broadcast explicitly.
    """
    location = character.location
    if location is not None and hasattr(location, "_broadcast_room_state"):
        location._broadcast_room_state()  # noqa: SLF001


def reroll_on_arrival(character: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """Per-room re-roll as a sneaking character arrives somewhere new.

    Success keeps the stance (the arrival announces anonymously); failure strips
    it quietly (the arrival is a normal, visible one — no attempt echo). Either
    way the room's one roll is spent. Returns whether the character is still
    hidden. No-op (False) for characters not sneak-concealed.
    """
    if not is_sneaking(character):
        return False
    mark_room_rolled(character)
    try:
        result = roll_sneak(character)
    except ValueError:
        # Stealth CheckType unseeded — fail toward visibility, never a stuck stance.
        stop_sneaking(character)
        refresh_room_state(character)
        return False
    if result.success_level > 0:
        return True
    stop_sneaking(character)
    refresh_room_state(character)
    return False
