"""Sun refuge search + auto-flee (#2846).

``find_sun_refuge`` walks the exit graph (the ``travel.find_route`` bulk-ORM
pattern) for the nearest room where *shade alone* zeroes the character's sun
exposure — indoors, or deep authored shadow. Clothing/magic deliberately don't
count: a refuge must be safe even if the character is nude and unwarded.
Non-public rooms (``room_is_publicly_listed``) win ties at equal depth — the
instinct is to hide somewhere private, per the #2846 spec.

``flee_to_sun_refuge`` performs the retreat: an IC event, narrated in both
rooms, never a silent teleport. Skips characters locked in active combat —
combat's own flee rules govern there. With no reachable refuge it returns
False and the guarded abandonment pool (ADR-0049) remains the backstop.
"""

from __future__ import annotations

from world.species.sun_constants import SUN_REFUGE_MAX_DEPTH


def find_sun_refuge(character, *, max_depth: int = SUN_REFUGE_MAX_DEPTH):
    """Nearest reachable room whose shade-only sun exposure is zero, or None.

    Breadth-first over exits from the character's location. Among refuges at
    the same (minimal) depth, a non-publicly-listed room wins.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from evennia_extensions.models import room_is_publicly_listed  # noqa: PLC0415

    origin = character.location
    if origin is None:
        return None
    visited: set[int] = {origin.pk}
    frontier: list[int] = [origin.pk]
    rooms_by_pk: dict[int, object] = {}
    for _depth in range(max_depth):
        if not frontier:
            break
        exits = ObjectDB.objects.filter(
            db_location_id__in=frontier,
            db_destination__isnull=False,
        ).select_related("db_destination")
        next_frontier: list[int] = []
        candidates = []
        for exit_obj in exits:
            dest = exit_obj.db_destination
            if dest.pk in visited:
                continue
            visited.add(dest.pk)
            rooms_by_pk[dest.pk] = dest
            next_frontier.append(dest.pk)
            if _shade_only_safe(character, dest):
                candidates.append(dest)
        if candidates:
            for room in candidates:
                if not room_is_publicly_listed(room):
                    return room
            return candidates[0]
        frontier = next_frontier
    return None


def _shade_only_safe(character, room) -> bool:
    """Whether *room* zeroes the character's sun exposure by shade/roof alone."""
    from world.species.sun_exposure import _base_sunlight, _shade_value  # noqa: PLC0415

    base = _base_sunlight(room)
    if base <= 0:
        return True
    return _shade_value(character, room) >= base


def flee_to_sun_refuge(character) -> bool:
    """Retreat the character to the nearest sun refuge. Returns True on success.

    Narrated as the character's survival instinct — an IC event. The movement
    hook re-reconciles exposure at the destination, clearing (or downgrading)
    the condition there.
    """
    if _in_active_combat(character):
        return False
    refuge = find_sun_refuge(character)
    if refuge is None:
        return False
    origin = character.location
    name = character.key
    if origin is not None:
        origin.msg_contents(f"{name} recoils from the burning light and retreats to cover.")
    character.msg(
        "|ySearing light overwhelms you — instinct takes over and you retreat "
        "to the nearest shelter.|n"
    )
    moved = character.move_to(refuge, quiet=False)
    return bool(moved)


def _in_active_combat(character) -> bool:
    """Whether the character participates in an uncompleted combat encounter."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.combat.models import CombatParticipant  # noqa: PLC0415

    try:
        sheet = character.character_sheet
    except (AttributeError, ObjectDoesNotExist):
        return False
    if sheet is None:
        return False
    return CombatParticipant.objects.filter(
        character_sheet=sheet, encounter__completed_at__isnull=True
    ).exists()
