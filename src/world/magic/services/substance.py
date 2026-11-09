"""A gift's substance (#5018): the room reading a gift works through.

A shadow gift works through shadow, which is the room's lighting, falling. A caster with
a GIFT thread on a gift that has a substance (``GiftSubstance``) is stronger where the
room is rich in it and weaker where it is opposed. Every cast of that gift needs the
substance present; where it is missing the cast calls it up first, for a little anima and
resonance. Control covers small amounts, the same way control makes a cast free. She can
also call it up with no technique (``CallUpSubstanceAction``), and a scene's GM can mark
it present for the scene (``MarkSubstancePresentAction``).

What gets called up or marked is an ordinary room-reading row on the location cascade:
``substance:<sheet pk>`` for a caster (cleared when she leaves or goes offline) and
``scene_mark:<scene pk>:<gift pk>`` for a GM's mark (cleared when the scene ends). The
cascade sums every row, so everyone in the room reads the same place.

Never a refusal for anima: nothing here checks her anima. A call-up she cannot afford goes
through ``deduct_anima`` and the soulfray path like any expensive cast.
"""

from __future__ import annotations

from decimal import Decimal
import math
from typing import TYPE_CHECKING

from django.db import transaction

from world.locations.constants import STAT_CLAMPS, STAT_DEFAULTS, StatKey
from world.locations.models import LocationValueModifier
from world.locations.services import felt_reading, set_room_stat_modifier
from world.magic.constants import ResonanceValence, SubstanceDirection
from world.magic.models import CharacterResonance, GiftSubstance
from world.magic.types.substance import (
    CallUpOffer,
    MarkOutcome,
    SubstanceBlock,
    SubstanceCallUp,
    SubstancePlan,
    SurroundingsKind,
    SurroundingsLine,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Gift, ResonanceEnvironmentConfig, Thread
    from world.scenes.models import Scene

#: Source prefix of a caster's own called-up row: ``substance:<sheet pk>``.
CALL_UP_SOURCE_PREFIX = "substance:"
#: Source prefix of a GM's mark: ``scene_mark:<scene pk>:<gift pk>``.
SCENE_MARK_SOURCE_PREFIX = "scene_mark:"


def call_up_source(sheet: CharacterSheet) -> str:
    return f"{CALL_UP_SOURCE_PREFIX}{sheet.pk}"


def scene_mark_source(scene: Scene, gift: Gift) -> str:
    return f"{SCENE_MARK_SOURCE_PREFIX}{scene.pk}:{gift.pk}"


def substance_for_gift(gift: Gift | None) -> GiftSubstance | None:
    """The gift's substance, or its nearest ancestor's (a child gift uses its parent's)."""
    if gift is None:
        return None
    lineage = gift.lineage
    rows = {
        row.gift_id: row
        for row in GiftSubstance.objects.filter(gift_id__in=[g.pk for g in lineage])
    }
    for link in lineage:
        if link.pk in rows:
            return rows[link.pk]
    return None


def gift_thread_for(character: ObjectDB, gift: Gift) -> Thread | None:  # noqa: OBJECTDB_PARAM - a caster
    """Her GIFT thread covering ``gift`` (a direct hold first), or None (no sheet, no thread)."""
    from world.magic.services.techniques import _get_character_sheet  # noqa: PLC0415
    from world.magic.specialization.services import gift_threads_for  # noqa: PLC0415

    if _get_character_sheet(character) is None:
        return None
    threads = gift_threads_for(character, gift)
    return threads[0] if threads else None


def _present_steps(substance: GiftSubstance, config: ResonanceEnvironmentConfig) -> int:
    """Steps past ordinary that count as present: a share of a measure, rounded up."""
    return max(math.ceil(Decimal(substance.full_at * config.substance_present_pct) / 100), 1)


def _clamp_richness(steps: int, full_at: int) -> Decimal:
    value = Decimal(steps) / Decimal(full_at)
    return max(Decimal(-1), min(Decimal(1), value))


def _opposed_steps(room: ObjectDB, substance: GiftSubstance) -> int:  # noqa: OBJECTDB_PARAM
    if not substance.opposed_by:
        return 0
    stat = StatKey(substance.opposed_by)
    return felt_reading(room, stat_key=stat).value - STAT_DEFAULTS[stat]


def substance_richness(gift: Gift, room: ObjectDB | None) -> Decimal:  # noqa: OBJECTDB_PARAM
    """How rich ``room`` is in ``gift``'s substance, -1 (opposed) to +1 (full)."""
    substance = substance_for_gift(gift)
    if substance is None or room is None:
        return Decimal(0)
    stat = StatKey(substance.stat_key)
    sign = 1 if substance.direction == SubstanceDirection.RISING else -1
    main = sign * (felt_reading(room, stat_key=stat).value - STAT_DEFAULTS[stat])
    return _clamp_richness(main - _opposed_steps(room, substance), substance.full_at)


def _place_shift_pct(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a caster
    room: ObjectDB,  # noqa: OBJECTDB_PARAM - a room
    config: ResonanceEnvironmentConfig,
) -> int:
    """How much a place's own magic moves a call-up's cost: aligned cheaper, opposed dearer."""
    from world.magic.services.resonance_environment import (  # noqa: PLC0415
        evaluate_resonance_environment,
    )

    effect = evaluate_resonance_environment(caster=character, room=room, technique=None)
    if effect.magnitude <= 0:
        return 0
    shift = min(config.substance_place_cap_pct, effect.magnitude)
    if effect.valence == ResonanceValence.ALIGNED:
        return -shift
    if effect.valence == ResonanceValence.OPPOSED:
        return shift
    return 0


def _room_profile(room: ObjectDB) -> RoomProfile | None:  # noqa: OBJECTDB_PARAM - a room
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    try:
        return room.room_profile
    except RoomProfile.DoesNotExist:
        return None


def _row_for_present(
    *,
    room: ObjectDB,  # noqa: OBJECTDB_PARAM - a room
    substance: GiftSubstance,
    source: str,
    target_offset: int,
) -> tuple[int, int] | None:
    """The row value ``source`` needs for the reading to sit ``target_offset`` steps along.

    Returns ``(row_value, felt_after)``; ``None`` when a fixed setting holds the reading.
    The row alone never exceeds the reading's span, so one writer cannot run away.
    """
    stat = StatKey(substance.stat_key)
    sign = 1 if substance.direction == SubstanceDirection.RISING else -1
    low, high = STAT_CLAMPS[stat]
    without = felt_reading(room, stat_key=stat, exclude_source=source)
    if without.override is not None:
        return None
    target = max(low, min(high, STAT_DEFAULTS[stat] + sign * target_offset))
    span = high - low
    row_value = max(-span, min(span, target - without.raw))
    felt_after = max(low, min(high, without.raw + row_value))
    return row_value, felt_after


def plan_substance_call_up(
    *,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a caster
    gift: Gift | None,
    room: ObjectDB | None,  # noqa: OBJECTDB_PARAM - a room
    control_surplus: int,
) -> SubstancePlan:
    """What calling up ``gift``'s substance in ``room`` would take and do. Pure read.

    The cast card, the cast's charge, its power line and the no-technique call-up all read
    this plan. ``control_surplus`` is the control she has left after the rest of what she
    is paying for, which covers that much of the call-up's anima (and the matching share
    of its resonance).
    """
    from world.magic.services.resonance_environment import (  # noqa: PLC0415
        get_resonance_environment_config,
    )

    if gift is None or room is None:
        return SubstancePlan()
    thread = gift_thread_for(character, gift)
    if thread is None:
        return SubstancePlan()
    substance = substance_for_gift(thread.target_gift)
    if substance is None:
        return SubstancePlan()
    config = get_resonance_environment_config()
    stat = StatKey(substance.stat_key)
    sign = 1 if substance.direction == SubstanceDirection.RISING else -1
    before = felt_reading(room, stat_key=stat).value
    opposed = _opposed_steps(room, substance)
    current = sign * (before - STAT_DEFAULTS[stat]) - opposed
    present = _present_steps(substance, config)
    richness_before = _clamp_richness(current, substance.full_at)
    base = SubstancePlan(
        substance=substance,
        gift=thread.target_gift,
        thread_level=thread.level,
        resonance=thread.resonance,
        room=room,
        steps_needed=max(present - current, 0),
        richness_before=richness_before,
        richness_after=richness_before,
    )
    if base.steps_needed == 0:
        return base
    profile = _room_profile(room)
    if profile is None:
        return _replace(base, blocked=SubstanceBlock.NO_PLACE)
    sheet = thread.owner
    placed = _row_for_present(
        room=room,
        substance=substance,
        source=call_up_source(sheet),
        target_offset=present + opposed,
    )
    if placed is None:
        return _replace(base, blocked=SubstanceBlock.HELD_FIXED)
    row_value, felt_after = placed
    steps_moved = sign * (felt_after - before)
    if steps_moved <= 0:
        return _replace(base, blocked=SubstanceBlock.HELD_FIXED)

    shift = _place_shift_pct(character, room, config)
    factor = (Decimal(100) + Decimal(shift)) / Decimal(100)
    measures = Decimal(steps_moved) / Decimal(substance.full_at)
    call_up_anima = math.ceil(config.substance_anima_per_measure * measures * factor)
    full_resonance = math.ceil(config.substance_resonance_per_measure * measures * factor)
    covered = min(call_up_anima, max(control_surplus, 0))
    if call_up_anima:
        resonance_cost = math.ceil(
            Decimal(full_resonance) * (call_up_anima - covered) / call_up_anima
        )
    else:
        resonance_cost = full_resonance
    balance = (
        CharacterResonance.objects.filter(character_sheet=sheet, resonance=thread.resonance)
        .values_list("balance", flat=True)
        .first()
        or 0
    )
    if balance < resonance_cost:
        return _replace(base, blocked=SubstanceBlock.TOO_LITTLE_RESONANCE)
    return _replace(
        base,
        room_profile=profile,
        steps_moved=steps_moved,
        row_value=row_value,
        call_up_anima=call_up_anima,
        covered_anima=covered,
        resonance_cost=resonance_cost,
        place_shift_pct=shift,
        richness_after=_clamp_richness(current + steps_moved, substance.full_at),
    )


def _replace(plan: SubstancePlan, **changes: object) -> SubstancePlan:
    from dataclasses import replace  # noqa: PLC0415

    return replace(plan, **changes)


def substance_power(plan: SubstancePlan) -> int:
    """The power line a cast reads from its plan: richness after any call-up, by thread level.

    Scaled by her GIFT thread's shown level through ``thread_level_multiplier``: 0.1 at
    level 1, 1.0 at level 10. The shown level is floored at 1 (the multiplier returns full
    strength at 0).
    """
    from world.magic.services.resonance_environment import (  # noqa: PLC0415
        get_resonance_environment_config,
    )
    from world.magic.services.threads import (  # noqa: PLC0415
        shown_thread_level,
        thread_level_multiplier,
    )

    if plan.is_empty or plan.richness_after == 0:
        return 0
    config = get_resonance_environment_config()
    level = max(shown_thread_level(plan.thread_level), 1)
    return round(
        plan.richness_after
        * Decimal(config.substance_power_at_full)
        * thread_level_multiplier(level)
    )


def apply_substance_plan(plan: SubstancePlan, *, sheet: CharacterSheet) -> SubstanceCallUp | None:
    """Write what a call-up does: her room row, her resonance, the room's line (#5018).

    Anima is charged by the caller (the cast's one ``deduct_anima``, or the no-technique
    action's), never here. The room line comes from the Narrator and names no one, and is
    sent only when the row actually changed.
    """
    if not plan.calls_up or plan.substance is None or plan.room_profile is None:
        return None
    from world.scenes.narrator import narrate_room_outcome  # noqa: PLC0415

    with transaction.atomic():
        resonance_taken = 0
        if plan.resonance_cost > 0 and plan.resonance is not None:
            row = (
                CharacterResonance.objects.select_for_update()
                .filter(character_sheet=sheet, resonance=plan.resonance)
                .first()
            )
            if row is not None:
                resonance_taken = min(row.balance, plan.resonance_cost)
                row.balance -= resonance_taken
                row.save(update_fields=["balance"])
        set_room_stat_modifier(
            plan.room_profile,
            StatKey(plan.substance.stat_key),
            source=call_up_source(sheet),
            value=plan.row_value,
        )
    if plan.room is not None and plan.substance.arrival_line:
        narrate_room_outcome(plan.room, plan.substance.arrival_line)
    return SubstanceCallUp(
        label=plan.substance.label,
        anima=plan.uncovered_anima,
        resonance=resonance_taken,
        resonance_name=plan.resonance.name if plan.resonance is not None else "",
        room_changed=True,
    )


def clear_caster_substance(
    sheet: CharacterSheet,
    *,
    keep_room: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM
) -> int:
    """Delete what she called up, everywhere but ``keep_room`` (she left, or went offline)."""
    rows = LocationValueModifier.objects.filter(source=call_up_source(sheet))
    if keep_room is not None:
        profile = _room_profile(keep_room)
        if profile is not None:
            rows = rows.exclude(room_profile=profile)
    deleted, _ = rows.delete()
    return deleted


def clear_scene_substance_marks(scene: Scene) -> int:
    """Delete every substance mark the scene's GM set (the scene ended)."""
    deleted, _ = LocationValueModifier.objects.filter(
        source__startswith=f"{SCENE_MARK_SOURCE_PREFIX}{scene.pk}:"
    ).delete()
    return deleted


def mark_substance_present(
    *,
    scene: Scene,
    substance: GiftSubstance,
    room: ObjectDB,  # noqa: OBJECTDB_PARAM - a room
    present: bool,
) -> str:
    """Mark ``substance`` present in ``room`` for ``scene`` (or remove the mark). Returns a
    plain outcome word: ``marked``, ``already``, ``removed``, ``held_fixed``, ``no_place``.

    The mark is just what brings the reading to present, read without the mark itself, so
    removing it puts the room back exactly as it was.
    """
    from world.magic.services.resonance_environment import (  # noqa: PLC0415
        get_resonance_environment_config,
    )

    profile = _room_profile(room)
    if profile is None:
        return MarkOutcome.NO_PLACE
    source = scene_mark_source(scene, substance.gift)
    stat = StatKey(substance.stat_key)
    if not present:
        set_room_stat_modifier(profile, stat, source=source, value=0)
        return MarkOutcome.REMOVED
    config = get_resonance_environment_config()
    sign = 1 if substance.direction == SubstanceDirection.RISING else -1
    without = felt_reading(room, stat_key=stat, exclude_source=source)
    if without.override is not None:
        return MarkOutcome.HELD_FIXED
    opposed = _opposed_steps(room, substance)
    current = sign * (without.value - STAT_DEFAULTS[stat]) - opposed
    present_steps = _present_steps(substance, config)
    if current >= present_steps:
        set_room_stat_modifier(profile, stat, source=source, value=0)
        return MarkOutcome.ALREADY
    placed = _row_for_present(
        room=room, substance=substance, source=source, target_offset=present_steps + opposed
    )
    if placed is None:
        return MarkOutcome.HELD_FIXED
    set_room_stat_modifier(profile, stat, source=source, value=placed[0])
    return MarkOutcome.MARKED


def scene_substance_marks(scene: Scene) -> list[GiftSubstance]:
    """The substances marked present in ``scene`` (for the GM's list)."""
    sources = LocationValueModifier.objects.filter(
        source__startswith=f"{SCENE_MARK_SOURCE_PREFIX}{scene.pk}:"
    ).values_list("source", flat=True)
    gift_ids = {int(source.rsplit(":", 1)[1]) for source in sources}
    return list(GiftSubstance.objects.filter(gift_id__in=gift_ids).select_related("gift"))


def surroundings_lines(plan: SubstancePlan) -> list[SurroundingsLine]:
    """The lines a cast card shows for its plan, under its cost (#5018)."""
    if plan.is_empty:
        return []
    label = plan.label
    lines: list[SurroundingsLine] = []
    if plan.calls_up:
        if plan.uncovered_anima == 0 and plan.resonance_cost == 0:
            text = f"Calls up {label}: free, your control covers it"
        else:
            resonance = plan.resonance.name if plan.resonance is not None else "resonance"
            text = (
                f"Calls up {label}: {plan.uncovered_anima} anima, "
                f"{plan.resonance_cost} {resonance} resonance"
            )
        lines.append(
            SurroundingsLine(
                kind=SurroundingsKind.CALL_UP,
                text=text,
                anima=plan.uncovered_anima,
                resonance=plan.resonance_cost,
            )
        )
    elif plan.blocked == SubstanceBlock.TOO_LITTLE_RESONANCE:
        lines.append(
            SurroundingsLine(
                kind=SurroundingsKind.BLOCKED, text=f"Too little resonance to call up {label}"
            )
        )
    elif plan.blocked == SubstanceBlock.HELD_FIXED:
        lines.append(
            SurroundingsLine(
                kind=SurroundingsKind.BLOCKED,
                text=f"This place is held fixed; {label} cannot be called up",
            )
        )
    power = substance_power(plan)
    if power > 0:
        where = "here after the call-up" if plan.calls_up else "here"
        lines.append(
            SurroundingsLine(
                kind=SurroundingsKind.POWER, text=f"{label.capitalize()} {where}", amount=power
            )
        )
    elif power < 0:
        lines.append(
            SurroundingsLine(kind=SurroundingsKind.POWER, text=_opposed_text(plan), amount=power)
        )
    return lines


def _opposed_text(plan: SubstancePlan) -> str:
    """How the card says the room is against her: "Too bright here" for shadow."""
    substance = plan.substance
    if substance is not None and substance.stat_key == StatKey.LIGHTING:
        falling = substance.direction == SubstanceDirection.FALLING
        return "Too bright here" if falling else "Too dark here"
    return f"Too little {plan.label} here"


def call_up_offers(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a caster
    *,
    lethal: bool = True,
) -> list[CallUpOffer]:
    """Every gift she can call up the substance of with no technique, priced now (#5018).

    One per GIFT thread whose gift (or an ancestor) has a substance. Priced by her own
    control alone (``get_runtime_caster_stats``): outside a fight the social safety bonus
    usually covers it. Never filtered by anima.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models import CharacterAnima  # noqa: PLC0415
    from world.magic.services.techniques import (  # noqa: PLC0415
        _get_character_sheet,
        calculate_effective_anima_cost,
        get_runtime_caster_stats,
    )

    if _get_character_sheet(character) is None:
        return []
    stats = get_runtime_caster_stats(character)
    surplus = max(stats.control - stats.intensity, 0)
    current = (
        CharacterAnima.objects.filter(character_id=character.pk)
        .values_list("current", flat=True)
        .first()
        or 0
    )
    offers: list[CallUpOffer] = []
    seen: set[int] = set()
    for thread in character.threads.all():
        if thread.target_kind != TargetKind.GIFT or thread.target_gift_id is None:
            continue
        substance = substance_for_gift(thread.target_gift)
        if substance is None or substance.gift_id in seen:
            continue
        seen.add(substance.gift_id)
        plan = plan_substance_call_up(
            character=character,
            gift=thread.target_gift,
            room=character.location,
            control_surplus=surplus,
        )
        if plan.is_empty:
            continue
        cost = calculate_effective_anima_cost(
            base_cost=plan.call_up_anima,
            runtime_intensity=stats.intensity,
            runtime_control=stats.control,
            current_anima=current,
            lethal=lethal,
        )
        offers.append(CallUpOffer(plan=plan, effective_cost=cost.effective_cost))
    return offers
