"""Calling up a gift's substance, and the power its Primum adds to a cast (#5018, #5125).

A fire gift works through fire. A caster with a GIFT thread on a gift that has a substance
draws on every source of Primum that counts for her (``primum.cast_points``): the place's
stock and call-ups of her own substance and of related or opposed ones, and the Primum items
she carries. The points add into one bonus on the authored curve, scaled by her thread.

Calling up raises the place's Primum of her substance by one step for one shared anima cost
(``ResonanceEnvironmentConfig.substance_call_up_anima``). A cast in a place with none of her
substance calls it up automatically, but only to the first step (Trace). She can also call it
up with no technique (``CallUpSubstanceAction``), and a scene's GM can mark it present for the
scene (``MarkSubstancePresentAction``). A call-up is a ``PrimumCallUp`` row: hers vanishes when
she leaves or goes offline, the GM's when the scene ends.

Never a refusal for anima: nothing here checks her anima. A call-up she cannot afford goes
through ``deduct_anima`` and the soulfray path like any expensive cast. No resonance is read
or written here.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import ResonanceValence
from world.magic.models import PrimumCallUp, PrimumStep, Substance
from world.magic.services.primum import (
    apportion_power,
    cast_points,
    gift_substance,
    held_amount,
    ordinary_leans,
    place_amount,
    power_for_points,
    total_points,
)
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
    from decimal import Decimal

    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Gift, ResonanceEnvironmentConfig, Thread
    from world.magic.types.primum import SourcePoints
    from world.scenes.models import Scene


def substance_for_gift(gift: Gift | None) -> Substance | None:
    """The gift's substance, or its nearest ancestor's (a child gift uses its parent's)."""
    return gift_substance(gift)


def gift_thread_for(character: ObjectDB, gift: Gift) -> Thread | None:  # noqa: OBJECTDB_PARAM - a caster
    """Her GIFT thread covering ``gift`` (a direct hold first), or None (no sheet, no thread)."""
    from world.magic.specialization.services import gift_threads_for  # noqa: PLC0415

    if character.character_sheet is None:
        return None
    threads = gift_threads_for(character, gift)
    return threads[0] if threads else None


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


def _call_up_target(
    steps: list[PrimumStep], amount: int, *, to_trace_only: bool
) -> tuple[int | None, str]:
    """The amount a call-up raises the place to, or None, and why nothing when it is blocked.

    The cast path raises a place below the first step to that step and leaves any other place
    alone. The no-technique path raises the place to the start of the next step; at the top
    step (or with no steps) nothing more can be called up.
    """
    if to_trace_only:
        if steps and amount < steps[0].starts_at:
            return steps[0].starts_at, SubstanceBlock.NONE
        return None, SubstanceBlock.NONE
    following = next((step for step in steps if step.starts_at > amount), None)
    if following is None:
        return None, SubstanceBlock.AT_TOP
    return following.starts_at, SubstanceBlock.NONE


def plan_substance_call_up(  # noqa: PLR0913 - keyword-only reads of one plan, no natural grouping
    *,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a caster
    gift: Gift | None,
    room: ObjectDB | None,  # noqa: OBJECTDB_PARAM - a room
    control_surplus: int,
    to_trace_only: bool = False,
    with_lines: bool = True,
) -> SubstancePlan:
    """What calling up ``gift``'s substance in ``room`` would take and do. Pure read.

    The cast card, the cast's charge, its power lines and the no-technique call-up all read
    this plan. ``control_surplus`` is the control she has left after the rest of what she is
    paying for, which covers that much of the call-up's anima. ``to_trace_only`` is the cast
    path: it calls up only where the place holds less than the first step. ``with_lines=False``
    skips the power-line queries for a caller that only reads the call-up (the enhancement
    index, the combat call-up offers); ``lines`` is then empty.
    """
    from world.magic.services.resonance_environment import (  # noqa: PLC0415
        get_resonance_environment_config,
    )

    if gift is None or room is None:
        return SubstancePlan()
    thread = gift_thread_for(character, gift)
    if thread is None:
        return SubstancePlan()
    substance = substance_for_gift(gift)
    if substance is None:
        return SubstancePlan()
    profile = _room_profile(room)
    amount = place_amount(room, substance)
    call_up_amount = 0
    if profile is None:
        blocked = SubstanceBlock.NO_PLACE
    else:
        target, blocked = _call_up_target(
            list(PrimumStep.objects.all()), amount, to_trace_only=to_trace_only
        )
        if target is not None:
            call_up_amount = max(target - held_amount(room, substance), 0)
    call_up_anima = covered = shift = 0
    if call_up_amount:
        config = get_resonance_environment_config()
        shift = _place_shift_pct(character, room, config)
        call_up_anima = math.ceil(config.substance_call_up_anima * (100 + shift) / 100)
        covered = min(call_up_anima, max(control_surplus, 0))
    return SubstancePlan(
        substance=substance,
        gift=thread.target_gift,
        thread_level=thread.level,
        room=room,
        room_profile=profile,
        current_amount=amount,
        call_up_amount=call_up_amount,
        blocked=blocked,
        call_up_anima=call_up_anima,
        covered_anima=covered,
        place_shift_pct=shift,
        lines=(
            tuple(cast_points(character, gift, room, extra_place_amount=call_up_amount))
            if with_lines
            else ()
        ),
    )


def _thread_multiplier(plan: SubstancePlan) -> Decimal:
    """Her GIFT thread's scaling: 0.1 at rung 1, 1.0 at rung 10 (rung floored at 1, #5091)."""
    from world.magic.services.threads import (  # noqa: PLC0415
        thread_level_multiplier,
        thread_rung,
    )

    return thread_level_multiplier(max(thread_rung(plan.thread_level), 1))


def substance_power(plan: SubstancePlan) -> int:
    """The power the plan's Primum sources add together, after any call-up it makes.

    The points sum into one value on the authored curve (capped there), then her GIFT
    thread scales it. 0 for an empty plan or a plan with no lines.
    """
    if plan.is_empty or not plan.lines:
        return 0
    return round(power_for_points(total_points(plan.lines)) * _thread_multiplier(plan))


def source_power_lines(plan: SubstancePlan) -> list[tuple[SourcePoints, int]]:
    """Each source with its signed share of ``substance_power(plan)``; zero shares dropped.

    The shares add up exactly to ``substance_power(plan)``: the positive lines split what they
    give on their own, and the negative lines split what they take away from that.
    """
    total = substance_power(plan)
    if not plan.lines:
        return []
    positive_points = sum(max(line.points, 0) for line in plan.lines)
    positive = round(power_for_points(positive_points) * _thread_multiplier(plan))
    shares = apportion_power(plan.lines, total, positive_power=positive)
    return [(line, share) for line, share in zip(plan.lines, shares, strict=True) if share]


def apply_substance_plan(plan: SubstancePlan, *, sheet: CharacterSheet) -> SubstanceCallUp | None:
    """Write what a call-up does: her ``PrimumCallUp`` row and the room's line (#5125).

    Anima is charged by the caller (the cast's one ``deduct_anima``, or the no-technique
    action's), never here. The room line names her by the face she presents.
    """
    if not plan.calls_up or plan.substance is None or plan.room_profile is None:
        return None
    from world.scenes.narrator import narrate_room_outcome  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    with transaction.atomic():
        row, created = PrimumCallUp.objects.get_or_create(
            room_profile=plan.room_profile,
            substance=plan.substance,
            caster=sheet,
            defaults={"amount_added": plan.call_up_amount},
        )
        if not created:
            # Read as a value under lock, never from the identity-mapped instance.
            current = (
                PrimumCallUp.objects.select_for_update()
                .filter(pk=row.pk)
                .values_list("amount_added", flat=True)
                .get()
            )
            row.amount_added = current + plan.call_up_amount
            row.save(update_fields=["amount_added"])
    if plan.room is not None:
        name = active_persona_for_sheet(sheet).name
        narrate_room_outcome(
            plan.room, f"{name} begins to manifest {plan.substance.name} in the area."
        )
    return SubstanceCallUp(label=plan.label, anima=plan.uncovered_anima, room_changed=True)


def clear_caster_substance(
    sheet: CharacterSheet,
    *,
    keep_room: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM
) -> int:
    """Delete what she called up, everywhere but ``keep_room`` (she left, or went offline)."""
    rows = PrimumCallUp.objects.filter(caster=sheet)
    if keep_room is not None:
        profile = _room_profile(keep_room)
        if profile is not None:
            rows = rows.exclude(room_profile=profile)
    deleted, _ = rows.delete()
    return deleted


def clear_scene_substance_marks(scene: Scene) -> int:
    """Delete every substance mark the scene's GM set (the scene ended)."""
    deleted, _ = PrimumCallUp.objects.filter(scene=scene).delete()
    return deleted


@transaction.atomic
def mark_substance_present(
    *,
    scene: Scene,
    substance: Substance,
    room: ObjectDB,  # noqa: OBJECTDB_PARAM - a room
    present: bool,
) -> str:
    """Mark ``substance`` present in ``room`` for ``scene`` (or remove the mark). Returns a
    plain outcome word: ``marked``, ``already``, ``removed``, ``no_place``.

    The mark is a scene ``PrimumCallUp`` holding just what raises the place to the first step
    (Trace), read without the mark itself, so removing it puts the place back as it was.
    """
    profile = _room_profile(room)
    if profile is None:
        return MarkOutcome.NO_PLACE
    marks = PrimumCallUp.objects.filter(room_profile=profile, substance=substance, scene=scene)
    if not present:
        marks.delete()
        return MarkOutcome.REMOVED
    first = PrimumStep.objects.order_by("rank").first()
    mark = marks.first()
    held_without = held_amount(room, substance) - (mark.amount_added if mark else 0)
    if first is None or ordinary_leans(room, substance) or held_without >= first.starts_at:
        marks.delete()
        return MarkOutcome.ALREADY
    needed = first.starts_at - held_without
    if mark is None:
        PrimumCallUp.objects.create(
            room_profile=profile, substance=substance, scene=scene, amount_added=needed
        )
    else:
        mark.amount_added = needed
        mark.save(update_fields=["amount_added"])
    return MarkOutcome.MARKED


def scene_substance_marks(scene: Scene) -> list[Substance]:
    """The substances marked present in ``scene`` (for the GM's list)."""
    return list(Substance.objects.filter(call_ups__scene=scene).distinct())


def surroundings_lines(plan: SubstancePlan) -> list[SurroundingsLine]:
    """The lines a cast card shows for its plan, under its cost (#5125).

    A call-up line when the cast calls her substance up, then one power line per source with
    its share of the power. A source working against her reads its already-redacted label.
    """
    if plan.is_empty:
        return []
    lines: list[SurroundingsLine] = []
    if plan.calls_up:
        uncovered = plan.uncovered_anima
        lines.append(
            SurroundingsLine(
                kind=SurroundingsKind.CALL_UP,
                text=_call_up_text(plan),
                anima=uncovered,
                detail="free, your control covers it" if uncovered == 0 else f"{uncovered} anima",
            )
        )
    lines.extend(
        SurroundingsLine(kind=SurroundingsKind.POWER, text=source.label, amount=power)
        for source, power in source_power_lines(plan)
    )
    return lines


def _call_up_text(plan: SubstancePlan) -> str:
    """ "Calls up fire", noting when the place's own magic moves the cost."""
    text = f"Calls up {plan.label}"
    if plan.place_shift_pct < 0:
        return f"{text}, the place makes it cheaper"
    if plan.place_shift_pct > 0:
        return f"{text}, the place makes it dearer"
    return text


def substance_gift_ids(character: ObjectDB) -> set[int]:  # noqa: OBJECTDB_PARAM - a caster
    """Every gift whose casts read Primum for her: the lineage of each GIFT thread of hers
    whose gift (or an ancestor) has a substance. Cached threads; one query per gift thread."""
    from world.magic.constants import TargetKind  # noqa: PLC0415

    if character.character_sheet is None:
        return set()
    covered: set[int] = set()
    for thread in character.threads.all():
        if thread.target_kind != TargetKind.GIFT or thread.target_gift_id is None:
            continue
        if substance_for_gift(thread.target_gift) is not None:
            covered |= set(thread.target_gift.lineage_ids)
    return covered


def call_up_offers(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a caster
    *,
    lethal: bool = True,
) -> list[CallUpOffer]:
    """Every substance of her own gifts she can call up with no technique, priced now.

    One per substance her GIFT threads work through; a related substance is never offered.
    Priced by her own control alone (``get_runtime_caster_stats``): outside a fight the social
    safety bonus usually covers it. Never filtered by anima.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models import CharacterAnima  # noqa: PLC0415
    from world.magic.services.techniques import (  # noqa: PLC0415
        calculate_effective_anima_cost,
        get_runtime_caster_stats,
    )

    # The cached sheet and threads handler first, so a character with no gift that has a
    # substance (most of them) costs nothing here: the combat payload reads this per row.
    if character.character_sheet is None:
        return []
    candidates = []
    seen: set[int] = set()
    for thread in character.threads.all():
        if thread.target_kind != TargetKind.GIFT or thread.target_gift_id is None:
            continue
        substance = substance_for_gift(thread.target_gift)
        if substance is None or substance.pk in seen:
            continue
        seen.add(substance.pk)
        candidates.append(thread)
    if not candidates:
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
    for thread in candidates:
        plan = plan_substance_call_up(
            character=character,
            gift=thread.target_gift,
            room=character.location,
            control_surplus=surplus,
            with_lines=False,
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
        offers.append(
            CallUpOffer(plan=plan, effective_cost=cost.effective_cost, current_anima=current)
        )
    return offers
