"""Reading Primum: what a place holds, what a cast draws on, and the power it adds (#5125).

Everything here is a read; nothing writes. Code compares substance rows and their relation
rows, never a gift or substance by name. A caster's own substance counts in full, a related
one for ``substance_related_share_pct``, an opposed one against her, and every other
substance not at all (relations never chain).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from django.db.models import Sum

from evennia_extensions.models import RoomProfile
from world.items.services.primum_items import item_substance_rows
from world.locations.constants import STAT_DEFAULTS, StatKey
from world.locations.services import felt_reading
from world.magic.constants import (
    GiftKind,
    PrimumLineKind,
    SubstanceDirection,
    SubstanceRelationKind,
)
from world.magic.models import (
    Gift,
    PlacePrimum,
    PrimumCallUp,
    PrimumStep,
    Substance,
    SubstancePowerStep,
)
from world.magic.services.resonance_environment import get_resonance_environment_config
from world.magic.services.substance_relations import relation_kinds_for
from world.magic.types.primum import SourcePoints

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet

_FULL_PERCENT = 100


def gift_substance(gift: Gift | None) -> Substance | None:
    """The substance ``gift`` works through: its own, else its nearest ancestor's.

    A minor gift has none, and neither does a gift whose whole lineage names none.
    """
    if gift is None or gift.kind == GiftKind.MINOR:
        return None
    for held in gift.lineage:
        if held.substance_id is not None:
            return held.substance
    return None


def ordinary_leans(room: ObjectDB, substance: Substance) -> bool:
    """Whether the room's ordinary condition leans the way ``substance`` grows.

    A substance with no room condition never leans. A reading on the other side of an ordinary
    room counts for nothing, not as a deficit.
    """
    if not substance.stat_key:
        return False
    stat_key = StatKey(substance.stat_key)
    sign = 1 if substance.direction == SubstanceDirection.RISING else -1
    return sign * (felt_reading(room, stat_key=stat_key).value - STAT_DEFAULTS[stat_key]) > 0


def _steps() -> list[PrimumStep]:
    return list(PrimumStep.objects.all())


def _step_in(steps: Sequence[PrimumStep], amount: int) -> PrimumStep | None:
    reached = [step for step in steps if step.starts_at <= amount]
    return max(reached, key=lambda step: step.rank) if reached else None


def step_for(amount: int) -> PrimumStep | None:
    """The highest step ``amount`` reaches, or None with no steps or an amount below the first."""
    return _step_in(_steps(), amount)


def step_names_for(amounts: Sequence[int]) -> list[str]:
    """The step name each amount reads as ("" below the first step), with one read of the steps."""
    steps = _steps()
    names = []
    for amount in amounts:
        step = _step_in(steps, amount)
        names.append(step.name if step is not None else "")
    return names


def _profile(room: ObjectDB) -> RoomProfile | None:
    try:
        return room.room_profile
    except RoomProfile.DoesNotExist:
        return None


def _held_amounts(
    profile: RoomProfile, now: datetime | None, substance_ids: Sequence[int] | None = None
) -> dict[int, int]:
    """Substance pk to authored stock plus call-ups in ``profile``'s place, floors not applied."""
    places = PlacePrimum.objects.filter(room_profile=profile)
    call_ups = PrimumCallUp.objects.filter(room_profile=profile)
    if substance_ids is not None:
        places = places.filter(substance_id__in=substance_ids)
        call_ups = call_ups.filter(substance_id__in=substance_ids)
    held: dict[int, int] = {}
    for place in places:
        held[place.substance_id] = held.get(place.substance_id, 0) + place.current_amount(now)
    for row in call_ups.values("substance_id").annotate(total=Sum("amount_added")):
        held[row["substance_id"]] = held.get(row["substance_id"], 0) + row["total"]
    return held


def held_amount(room: ObjectDB, substance: Substance, *, now: datetime | None = None) -> int:
    """The Primum of ``substance`` ``room`` actually holds: stock and call-ups, no floor.

    A call-up raising the place to an amount adds the difference from this, not from
    ``place_amount``, whose ordinary-condition floor is not held Primum. A room with no
    ``RoomProfile`` holds nothing.
    """
    profile = _profile(room)
    if profile is None:
        return 0
    return _held_amounts(profile, now, [substance.pk]).get(substance.pk, 0)


def place_amount(
    room: ObjectDB, substance: Substance, *, extra: int = 0, now: datetime | None = None
) -> int:
    """The Primum of ``substance`` in ``room``: stock, call-ups and ``extra``.

    A room whose ordinary condition leans the way ``substance`` grows reads at least the first
    step's start. A room with no ``RoomProfile`` holds nothing, so reads just ``extra``.
    """
    profile = _profile(room)
    if profile is None:
        return extra
    held = _held_amounts(profile, now, [substance.pk]).get(substance.pk, 0) + extra
    if ordinary_leans(room, substance):
        steps = _steps()
        if steps:
            held = max(held, steps[0].starts_at)
    return held


def room_substance_amounts(room: ObjectDB, *, now: datetime | None = None) -> dict[int, int]:
    """Substance pk to the Primum in ``room``, for every substance with any (zeros omitted)."""
    profile = _profile(room)
    if profile is None:
        return {}
    amounts = _held_amounts(profile, now)
    steps = _steps()
    if steps:
        for substance in Substance.objects.exclude(stat_key=""):
            if ordinary_leans(room, substance):
                amounts[substance.pk] = max(amounts.get(substance.pk, 0), steps[0].starts_at)
    return {pk: amount for pk, amount in amounts.items() if amount > 0}


def _capitalised(name: str) -> str:
    return name[:1].upper() + name[1:]


def _factor(own: Substance, other_id: int, relations: Mapping[int, str], share_pct: int) -> int:
    """How much of a source of ``other_id`` counts to a caster of ``own``, as a percent."""
    if other_id == own.pk:
        return _FULL_PERCENT
    kind = relations.get(other_id)
    if kind == SubstanceRelationKind.RELATED:
        return share_pct
    if kind == SubstanceRelationKind.OPPOSED:
        return -_FULL_PERCENT
    return 0


def cast_points(
    character: ObjectDB,
    gift: Gift,
    room: ObjectDB | None,
    *,
    extra_place_amount: int = 0,
) -> list[SourcePoints]:
    """Every source of Primum a cast of ``gift`` draws on, with signed points.

    One line per substance in ``room`` that counts and has points, and one per equipped item.
    ``extra_place_amount`` is added to the gift's own substance in the place (a call-up made
    for this cast). A gift with no substance, or no Primum steps, gives no lines.
    """
    own = gift_substance(gift)
    steps = _steps()
    if own is None or not steps:
        return []
    from world.magic.services.primum_perception import perceived_substance_ids  # noqa: PLC0415

    relations = relation_kinds_for(own)
    share_pct = get_resonance_environment_config().substance_related_share_pct
    if room is None:
        amounts = {own.pk: extra_place_amount} if extra_place_amount else {}
    else:
        amounts = room_substance_amounts(room)
        amounts[own.pk] = place_amount(room, own, extra=extra_place_amount)
    place_rows = _signed_points(own, amounts, steps, relations, share_pct)
    item_rows = _item_rows(character, own, relations, share_pct)
    names = {
        substance.pk: substance.name
        for substance in Substance.objects.filter(pk__in=[pk for pk, _ in place_rows])
    }
    perceived = (
        perceived_substance_ids(character, room)
        if any(points < 0 for _, points in place_rows)
        else frozenset()
    )
    lines: list[SourcePoints] = []
    for substance_id, points in place_rows:
        name = names[substance_id]
        if points < 0 and substance_id in perceived:
            label = f"{_capitalised(name)} here works against your {own.name}"
        elif points < 0:
            label = f"Something here works against your {own.name}"
        else:
            label = f"Surroundings: {name}"
        lines.append(
            SourcePoints(
                kind=PrimumLineKind.PLACE,
                label=label,
                points=points,
                substance_id=substance_id,
            )
        )
    lines.extend(item_rows)
    return lines


def _signed_points(
    own: Substance,
    amounts: Mapping[int, int],
    steps: Sequence[PrimumStep],
    relations: Mapping[int, str],
    share_pct: int,
) -> list[tuple[int, int]]:
    """(substance pk, signed points) for each place substance that counts, in pk order."""
    rows: list[tuple[int, int]] = []
    for substance_id in sorted(amounts):
        step = _step_in(steps, amounts[substance_id])
        if step is None:
            continue
        points = step.points * _factor(own, substance_id, relations, share_pct) // _FULL_PERCENT
        if points:
            rows.append((substance_id, points))
    return rows


def _item_rows(
    character: ObjectDB,
    own: Substance,
    relations: Mapping[int, str],
    share_pct: int,
) -> list[SourcePoints]:
    sheet = _sheet(character)
    if sheet is None:
        return []
    lines: list[SourcePoints] = []
    for row in item_substance_rows(sheet):
        factor = _factor(own, row.substance_id, relations, share_pct)
        points = row.step.points * factor // _FULL_PERCENT
        if points:
            lines.append(
                SourcePoints(
                    kind=PrimumLineKind.ITEM,
                    label=f"{row.item_instance.display_name} ({row.substance.name})",
                    points=points,
                    substance_id=row.substance_id,
                    item_id=row.item_instance_id,
                )
            )
    return lines


def _sheet(character: ObjectDB) -> CharacterSheet | None:
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    try:
        return character.sheet_data
    except CharacterSheet.DoesNotExist:
        return None


def total_points(lines: Sequence[SourcePoints]) -> int:
    """The signed points of every line added together."""
    return sum(line.points for line in lines)


def points_to_power(total: int, curve: Sequence[tuple[int, int]], *, cap: int) -> int:
    """The power ``total`` points reach on ``curve``, a list of ``(points_reached, power)``.

    Linear between the rows, starting from (0, 0), flat after the last row. A negative total
    mirrors the positive one. The result never passes ``cap`` either way. No rows gives 0.
    """
    magnitude = abs(total)
    if not curve or magnitude == 0:
        return 0
    previous_x, previous_y = 0, 0
    power = curve[-1][1]
    for x, y in sorted(curve):
        if magnitude <= x:
            power = previous_y + (magnitude - previous_x) * (y - previous_y) // (x - previous_x)
            break
        previous_x, previous_y = x, y
    power = min(power, cap)
    return power if total > 0 else -power


def power_for_points(total: int) -> int:
    """The power ``total`` points give on the authored curve, 0 when none is authored."""
    curve = [(row.points_reached, row.power) for row in SubstancePowerStep.objects.all()]
    if not curve:
        return 0
    return points_to_power(total, curve, cap=get_resonance_environment_config().substance_power_cap)


def _largest_remainder(weights: Sequence[int], amount: int) -> list[int]:
    """Split ``amount`` over ``weights`` by the largest remainder, earlier entries first on a tie.

    Entries with weight 0 get 0, and so does everyone when no weight is above 0.
    """
    weight_sum = sum(weights)
    if weight_sum == 0 or amount <= 0:
        return [0] * len(weights)
    shares = [amount * weight // weight_sum for weight in weights]
    by_remainder = sorted(
        (i for i, weight in enumerate(weights) if weight),
        key=lambda i: (-(amount * weights[i] % weight_sum), i),
    )
    for index in by_remainder[: amount - sum(shares)]:
        shares[index] += 1
    return shares


def apportion_power(
    lines: Sequence[SourcePoints], total_power: int, *, positive_power: int
) -> list[int]:
    """Split ``total_power`` across ``lines``, each line keeping the sign of its points.

    ``positive_power`` is the power the positive lines would give on their own (callers pass
    ``power_for_points`` of the positive points). Lines with positive points split it by their
    points; lines with negative points split what they take away, ``positive_power -
    total_power``, by their points, and each share is negated; a line worth no points gets 0.
    The shares add up to ``total_power`` when the lines hold both signs as the amounts imply.
    The total is never the divisor, so near-cancelling lines cannot blow a share up.
    """
    gained = _largest_remainder([max(line.points, 0) for line in lines], positive_power)
    lost = _largest_remainder(
        [max(-line.points, 0) for line in lines], positive_power - total_power
    )
    return [up - down for up, down in zip(gained, lost, strict=True)]
