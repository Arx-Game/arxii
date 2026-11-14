"""Retuning a thread: moving part of one of its resonances to another (#5123, ruling 31).

A thread holds several resonances on its ``ThreadResonance`` rows. A player performs the
SERVICE ritual whose ``service_function_path`` is ``THREAD_RESONANCE_SERVICE_PATH`` (staff
author the row and its component requirements) to move part of one row's amount to another
resonance's row on the same thread, because a thread at its cap cannot change its mix by
imbuing. Within the source resonance's affinity it is a retune, one to one. Across
affinities it is a Fall or a Redemption: the moved amount converts at the authored pair rate
(``conversion_pair``) toward the ``ResonanceConversion`` counterpart of the source
resonance, floored at 1 so a Redemption shrinks the amount but never loses it entirely.

A row moved down to nothing is deleted. The thread's ``level`` and ``developed_points`` are
untouched, and so are the character's
resonance balances and lifetime (the aura needs no recompute). Only the rows move, then
``refresh_leading_resonance`` follows who now leads.

No roll: the rite's anima requirement and components still apply through
``PerformRitualAction``, which calls ``check_thread_resonance_change`` before it spends
anything, so a refused move costs nothing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import RitualExecutionKind, TargetKind
from world.magic.exceptions import (
    ConversionMappingError,
    ThreadResonanceChangeError,
    UnknownOwnedThread,
    UnknownResonance,
)
from world.magic.models import Resonance, Ritual, Thread, ThreadResonance
from world.magic.models.fall_redemption import ConversionType, ResonanceConversion
from world.magic.seeds_sanctum import PURGING_RITUAL_NAME
from world.magic.services.conversion import conversion_pair
from world.magic.services.thread_rows import (
    gift_allowed_resonance_ids,
    refresh_leading_resonance,
)
from world.magic.types.threads import (
    ThreadResonanceChangeResult,
    ThreadResonanceOption,
    ThreadRetuneMove,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

THREAD_RESONANCE_SERVICE_PATH = "world.magic.services.thread_resonance.change_thread_resonance"

NO_THREAD_MESSAGE = UnknownOwnedThread.user_message
NAME_A_THREAD_MESSAGE = "Name the thread to move."
NAME_A_RESONANCE_MESSAGE = "Name the resonance to move it to."
AMOUNT_MESSAGE = "Name a whole number of points to move, at least 1."
NO_OPTIONS_MESSAGE = "This thread has no resonance it can move to."
NO_RITE_MESSAGE = "No ritual can change a thread's resonance yet."
SANCTUM_THREAD_MESSAGE = (
    f"A sanctum thread channels its sanctum's resonance; the {PURGING_RITUAL_NAME} changes it."
)
SIGNATURE_THREAD_MESSAGE = (
    "This thread's signature flourish is tied to a resonance; clear the signature before moving it."
)


def _id_from(raw: object) -> int | None:
    """``raw`` as an integer id, or None when it is not one (a bool, a list, "abc")."""
    if isinstance(raw, bool) or not isinstance(raw, int | str):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def resolve_target_resonance(resonance_id: object) -> Resonance:
    """Resolve the ``target_resonance`` id a ritual caller sends to its ``Resonance``.

    The one resolver the telnet ``ritual`` command and the web ritual-perform view share
    (the ``resolve_target_affinity`` shape). Raises ``UnknownResonance`` for a non-integer or
    unknown id.
    """
    pk = _id_from(resonance_id)
    resonance = None if pk is None else Resonance.objects.filter(pk=pk).first()
    if resonance is None:
        raise UnknownResonance(resonance_id)
    return resonance


def resolve_owned_thread(character_sheet: CharacterSheet, thread_id: object) -> Thread:
    """Resolve a ritual's thread id to one of ``character_sheet``'s live threads.

    Shared by the telnet ``ritual`` command and the web ritual-perform view. Raises
    ``UnknownOwnedThread`` for a non-integer id, someone else's thread, or a retired one.
    """
    pk = _id_from(thread_id)
    thread = (
        None
        if pk is None
        else Thread.objects.filter(pk=pk, owner=character_sheet, retired_at__isnull=True).first()
    )
    if thread is None:
        raise UnknownOwnedThread(thread_id)
    return thread


def thread_resonance_ritual() -> Ritual | None:
    """The authored SERVICE ritual that moves a thread, or None while staff have not made one."""
    return (
        Ritual.objects.filter(
            execution_kind=RitualExecutionKind.SERVICE,
            service_function_path=THREAD_RESONANCE_SERVICE_PATH,
        )
        .order_by("pk")
        .first()
    )


def scaled_thread_points(points: int, multiplier: Decimal) -> int:
    """``points`` at ``multiplier``, floored at 1 while there is anything to move."""
    if points <= 0:
        return 0
    return max(1, int(Decimal(points) * multiplier))


def thread_resonance_refusal(thread: Thread) -> str:
    """Why ``thread`` cannot move to any resonance at all, or "" when it may.

    Two anchors hold a thread's resonance in place (ruled on the final review of slice 6):
    a SANCTUM thread channels its sanctum's consecrated resonance, which the Ritual of
    Purging changes; a TECHNIQUE thread whose signature bonus requires a resonance would
    keep a flourish it no longer qualifies for, so the signature is cleared first.
    """
    if thread.target_kind == TargetKind.SANCTUM:
        return SANCTUM_THREAD_MESSAGE
    if (
        thread.signature_bonus_id is not None
        and thread.signature_bonus.required_resonance_id is not None
    ):
        return SIGNATURE_THREAD_MESSAGE
    return ""


def thread_row_amounts(thread: Thread) -> dict[int, int]:
    """``{resonance pk: amount}`` for each row ``thread`` holds, read in one query."""
    return dict(ThreadResonance.objects.filter(thread=thread).values_list("resonance_id", "amount"))


def _options_for(thread: Thread, source: Resonance, moving: int) -> list[ThreadResonanceOption]:
    """The options for moving ``moving`` points of ``source``'s row, sorted for display."""
    candidates: list[tuple[Resonance, str | None, Decimal]] = [
        (resonance, None, Decimal(1))
        for resonance in Resonance.objects.filter(affinity_id=source.affinity_id)
        .exclude(pk=source.pk)
        .select_related("affinity")
    ]
    mappings = (
        ResonanceConversion.objects.filter(source_resonance=source)
        .exclude(target_affinity_id=source.affinity_id)
        .select_related("target_affinity", "target_resonance__affinity")
    )
    for mapping in mappings:
        try:
            # Cached per process (AffinityInteraction.objects.interaction_for): no query.
            pair = conversion_pair(source.affinity, mapping.target_affinity)
        except ConversionMappingError:
            continue
        candidates.append(
            (mapping.target_resonance, pair.conversion_type, pair.conversion_multiplier)
        )
    allowed = gift_allowed_resonance_ids(thread)
    if allowed is not None:
        candidates = [c for c in candidates if c[0].pk in allowed]
    options = [
        ThreadResonanceOption(
            resonance=resonance,
            conversion_type=conversion_type,
            multiplier=multiplier,
            projected_points=scaled_thread_points(moving, multiplier),
        )
        for resonance, conversion_type, multiplier in candidates
    ]
    options.sort(
        key=lambda option: (
            option.conversion_type is not None,
            option.resonance.affinity.name,
            option.resonance.name,
        )
    )
    return options


def thread_resonance_options(
    thread: Thread, from_resonance: Resonance | None = None, amount: int | None = None
) -> list[ThreadResonanceOption]:
    """Every resonance part of ``from_resonance``'s row may be moved to, with what it would gain.

    ``from_resonance`` is a resonance the thread holds a row for (default: the leading one);
    ``amount`` is how much of that row would move (default: all of it). Every other resonance
    of the source's affinity (rate 1, no conversion type), and for each other affinity, the
    ``ResonanceConversion`` counterpart of the source resonance when an authored pair
    (``conversion_pair``) joins the two affinities. A target with no mapping or no pair is
    not offered. A thread ``thread_resonance_refusal`` holds in place has none, and neither
    has one that holds nothing in the source row; a GIFT thread is offered only its gift's
    supported resonances when the gift names any. ``projected_points`` is what the target's
    row gains. Sorted for display: own affinity first, then by affinity and resonance name.
    """
    if thread_resonance_refusal(thread):
        return []
    source = from_resonance or thread.resonance
    held = thread_row_amounts(thread).get(source.pk)
    if not held:
        return []
    return _options_for(thread, source, held if amount is None else amount)


def thread_resonance_unavailable_reason(
    thread: Thread, ritual: Ritual | None, options: list[ThreadResonanceOption]
) -> str:
    """Why the Spellbook cannot move ``thread`` now, or "" when it can.

    The thread's own refusal first (it holds whatever is authored), then a missing rite,
    then no options.
    """
    refusal = thread_resonance_refusal(thread)
    if refusal:
        return refusal
    if ritual is None:
        return NO_RITE_MESSAGE
    if not options:
        return NO_OPTIONS_MESSAGE
    return ""


def _thread_label(thread: Thread) -> str:
    """The thread's own name, else "Your <anchor> thread"."""
    from world.magic.crossing.handlers import anchor_label_for  # noqa: PLC0415

    return thread.name or f"Your {anchor_label_for(thread)} thread"


def change_message(  # noqa: PLR0913 - every number the line names
    label: str,
    *,
    from_name: str,
    to_name: str,
    amount_moved: int,
    points_gained: int,
    from_amount_after: int,
    to_amount_after: int,
) -> str:
    """The line a performer reads after a retune, telnet and web alike."""
    moved = f"{label} moved {amount_moved} {from_name} into {to_name}"
    if points_gained != amount_moved:
        moved += f", which became {points_gained}"
    if from_amount_after == 0:
        return f"{moved}. It holds no {from_name} now, and {to_amount_after} {to_name}."
    return f"{moved}. It now holds {from_amount_after} {from_name} and {to_amount_after} {to_name}."


def option_label(option: ThreadResonanceOption, *, with_id: bool = False) -> str:
    """ "Lumen (same affinity)", or with ``with_id`` "Lumen (12, same affinity)" for telnet."""
    kind = (
        "same affinity"
        if option.conversion_type is None
        else ConversionType(option.conversion_type).label
    )
    if with_id:
        return f"{option.resonance.name} ({option.resonance.pk}, {kind})"
    return f"{option.resonance.name} ({kind})"


def options_sentence(options: list[ThreadResonanceOption], *, with_ids: bool = False) -> str:
    """The "It can move to: ..." sentence; telnet asks for ids to type."""
    if not options:
        return NO_OPTIONS_MESSAGE
    labels = ", ".join(option_label(option, with_id=with_ids) for option in options)
    return f"It can move to: {labels}."


def resolve_retune_amount(raw: object) -> int | None:
    """The points a caller named to move, or None when it named none.

    The one resolver the telnet ``ritual`` command and the web ritual-perform view share.
    Raises ``ThreadResonanceChangeError`` for anything but a whole number of at least 1.
    """
    if raw is None:
        return None
    pk = _id_from(raw)
    if pk is None or pk < 1:
        raise ThreadResonanceChangeError(AMOUNT_MESSAGE)
    return pk


def _held_sentence(held: dict[int, int], names: dict[int, str]) -> str:
    """ "It holds: Fury 10, Domination 5." for the rows ``held`` names."""
    return "It holds: " + ", ".join(f"{names[pk]} {amount}" for pk, amount in held.items()) + "."


def _resolve_source_row(
    thread: Thread, from_resonance: Resonance | None, amount: int | None
) -> tuple[Resonance, int, int]:
    """``(source resonance, its row's amount, points to move)`` or a refusal; reads rows once."""
    source = from_resonance or thread.resonance
    held = thread_row_amounts(thread)
    if source.pk not in held:
        names = dict(Resonance.objects.filter(pk__in=held).values_list("pk", "name"))
        msg = f"This thread holds no {source.name}. {_held_sentence(held, names)}"
        raise ThreadResonanceChangeError(msg)
    available = held[source.pk]
    if available < 1:
        msg = f"This thread has no {source.name} to move."
        raise ThreadResonanceChangeError(msg)
    moving = available if amount is None else amount
    if moving < 1 or moving > available:
        msg = f"This thread holds {available} {source.name}; name an amount from 1 to {available}."
        raise ThreadResonanceChangeError(msg)
    return source, available, moving


def check_thread_resonance_change(
    character_sheet: CharacterSheet,
    *,
    thread: Thread | None,
    target_resonance: Resonance | None,
    from_resonance: Resonance | None = None,
    amount: int | None = None,
) -> ThreadRetuneMove:
    """Refuse a move that cannot be made; return the move to make. Writes nothing.

    ``from_resonance`` defaults to the thread's leading resonance and ``amount`` to all of
    that row. ``PerformRitualAction`` calls this before spending the rite's components and
    anima; ``change_thread_resonance`` calls it again under the thread's lock.

    Raises:
        ThreadResonanceChangeError: No thread named, a thread that is not the performer's or
            is retired, a thread its anchor holds in place (``thread_resonance_refusal``), a
            source resonance the thread holds no row for or holds none of, an amount past
            the row, no target named (the message lists the options), a target that is not
            among the options. The messages carry no telnet syntax; the ``ritual`` command
            adds its own hint before it dispatches.
    """
    if thread is None:
        raise ThreadResonanceChangeError(NAME_A_THREAD_MESSAGE)
    if thread.owner_id != character_sheet.pk or thread.retired_at is not None:
        raise ThreadResonanceChangeError(NO_THREAD_MESSAGE)
    refusal = thread_resonance_refusal(thread)
    if refusal:
        raise ThreadResonanceChangeError(refusal)
    source, available, moving = _resolve_source_row(thread, from_resonance, amount)
    options = _options_for(thread, source, moving)
    if target_resonance is None:
        msg = f"{NAME_A_RESONANCE_MESSAGE} {options_sentence(options)}"
        raise ThreadResonanceChangeError(msg)
    chosen = next((o for o in options if o.resonance.pk == target_resonance.pk), None)
    if chosen is None:
        msg = f"{source.name} cannot move to {target_resonance.name}. {options_sentence(options)}"
        raise ThreadResonanceChangeError(msg)
    return ThreadRetuneMove(
        from_resonance=source, from_amount=available, amount=moving, option=chosen
    )


@transaction.atomic
def change_thread_resonance(
    character_sheet: CharacterSheet,
    *,
    thread: Thread | None = None,
    target_resonance: Resonance | None = None,
    from_resonance: Resonance | None = None,
    amount: int | None = None,
    **_ritual_dispatch_kwargs: object,  # ritual dispatch also forwards ``ritual=``
) -> ThreadResonanceChangeResult:
    """Move ``amount`` of ``from_resonance``'s row on ``thread`` into ``target_resonance``'s.

    Locks the thread's rows, re-reads their amounts from the database (the identity map
    would answer from memory), and refuses through ``check_thread_resonance_change``. The
    source row loses ``amount``; the target's row (created when the thread holds none) gains
    it at the option's rate (``scaled_thread_points``). ``level`` and ``developed_points``
    are unchanged. The leading resonance is refreshed afterwards.

    Raises:
        ThreadResonanceChangeError: See ``check_thread_resonance_change``.
    """
    if thread is None:
        raise ThreadResonanceChangeError(NAME_A_THREAD_MESSAGE)
    # A filter, not get(): the identity map would answer get() without the lock.
    locked = Thread.objects.select_for_update().filter(pk=thread.pk)
    row = locked.values("owner_id", "retired_at").first()
    if row is None or row["owner_id"] != character_sheet.pk or row["retired_at"] is not None:
        raise ThreadResonanceChangeError(NO_THREAD_MESSAGE)
    held_rows = list(ThreadResonance.objects.select_for_update().filter(thread=thread))
    fresh = dict(
        ThreadResonance.objects.filter(thread=thread).values_list("resonance_id", "amount")
    )
    for held_row in held_rows:
        held_row.amount = fresh[held_row.resonance_id]
    move = check_thread_resonance_change(
        character_sheet,
        thread=thread,
        target_resonance=target_resonance,
        from_resonance=from_resonance,
        amount=amount,
    )
    label = _thread_label(thread)
    source_row = next(r for r in held_rows if r.resonance_id == move.from_resonance.pk)
    target = move.option.resonance
    target_row = next((r for r in held_rows if r.resonance_id == target.pk), None)
    gained = move.option.projected_points
    source_row.amount -= move.amount
    source_row.save(update_fields=["amount"])
    if target_row is None:
        target_row = ThreadResonance.objects.create(thread=thread, resonance=target, amount=gained)
    else:
        target_row.amount += gained
        target_row.save(update_fields=["amount"])
    if source_row.amount == 0:
        # An emptied row goes (the target row now exists, so it is never the only one).
        source_row.delete()
    refresh_leading_resonance(thread)
    character_sheet.character.threads.invalidate()
    return ThreadResonanceChangeResult(
        thread_id=thread.pk,
        from_resonance_id=move.from_resonance.pk,
        to_resonance_id=target.pk,
        amount_moved=move.amount,
        points_gained=gained,
        from_amount_after=source_row.amount,
        to_amount_after=target_row.amount,
        conversion_type=move.option.conversion_type,
        message=change_message(
            label,
            from_name=move.from_resonance.name,
            to_name=target.name,
            amount_moved=move.amount,
            points_gained=gained,
            from_amount_after=source_row.amount,
            to_amount_after=target_row.amount,
        ),
    )
