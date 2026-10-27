"""Moving one thread to another resonance (slice 6 of #4672).

A player performs the SERVICE ritual whose ``service_function_path`` is
``THREAD_RESONANCE_SERVICE_PATH`` (staff author the row and its component requirements) to
move one of their threads. Within the thread's own affinity it is a retune, one to one.
Across affinities it is a Fall or a Redemption: the thread's ``developed_points`` convert
at the authored pair rate (``conversion_pair``), toward the ``ResonanceConversion``
counterpart of its resonance, floored at 1 so a Redemption shrinks a thread but never
empties it. When the character already holds a live thread on the same anchor in the new
resonance, the two merge (the full conversion's ``_reanchor_thread``).

No roll: the rite's anima requirement and components still apply through
``PerformRitualAction``, which calls ``check_thread_resonance_change`` before it spends
anything, so a refused move costs nothing. Resonance balances are untouched, so the aura
(which sums ``lifetime_earned``) needs no recompute.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import RitualExecutionKind
from world.magic.exceptions import ConversionMappingError, ThreadResonanceChangeError
from world.magic.models import Resonance, Ritual, Thread
from world.magic.models.fall_redemption import ConversionType, ResonanceConversion
from world.magic.services.conversion import _reanchor_thread, conversion_pair
from world.magic.types.threads import ThreadResonanceChangeResult, ThreadResonanceOption

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

THREAD_RESONANCE_SERVICE_PATH = "world.magic.services.thread_resonance.change_thread_resonance"

NO_THREAD_MESSAGE = "You have no active thread with that id."
NAME_A_THREAD_MESSAGE = "Name the thread to move: thread=<id>."


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


def thread_resonance_options(thread: Thread) -> list[ThreadResonanceOption]:
    """Every resonance ``thread`` may be moved to, with the rate and the points it would hold.

    Every other resonance of the thread's affinity (rate 1, no conversion type), and for each
    other affinity, the ``ResonanceConversion`` counterpart of the thread's resonance when an
    authored pair (``conversion_pair``) joins the two affinities. A target with no mapping or
    no pair is not offered. Sorted for display: own affinity first, then by affinity and
    resonance name.
    """
    source = thread.resonance
    points = thread.developed_points
    options = [
        ThreadResonanceOption(
            resonance=resonance,
            conversion_type=None,
            multiplier=Decimal(1),
            projected_points=points,
        )
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
        options.append(
            ThreadResonanceOption(
                resonance=mapping.target_resonance,
                conversion_type=pair.conversion_type,
                multiplier=pair.conversion_multiplier,
                projected_points=scaled_thread_points(points, pair.conversion_multiplier),
            )
        )
    options.sort(
        key=lambda option: (
            option.conversion_type is not None,
            option.resonance.affinity.name,
            option.resonance.name,
        )
    )
    return options


def _thread_label(thread: Thread) -> str:
    """The thread's own name, else "Your <anchor> thread"."""
    from world.magic.crossing.handlers import _anchor_label_for  # noqa: PLC0415

    return thread.name or f"Your {_anchor_label_for(thread)} thread"


def change_message(  # noqa: PLR0913 - every number the line names
    label: str,
    *,
    from_name: str,
    to_name: str,
    points_before: int,
    points_moved: int,
    points_after: int,
    merged: bool,
) -> str:
    """The line a performer reads after a retune, telnet and web alike."""
    if merged:
        return (
            f"{label} left {from_name} and merged into your {to_name} thread on the same "
            f"anchor: its {points_before} points brought {points_moved}, and that thread "
            f"now holds {points_after}."
        )
    return (
        f"{label} left {from_name} and now channels {to_name} "
        f"({points_before} points, now {points_after})."
    )


def _option_label(option: ThreadResonanceOption) -> str:
    kind = (
        "same affinity"
        if option.conversion_type is None
        else ConversionType(option.conversion_type).label
    )
    return f"{option.resonance.name} ({option.resonance.pk}, {kind})"


def _options_sentence(options: list[ThreadResonanceOption]) -> str:
    if not options:
        return "This thread has no resonance it can move to."
    return "It can move to: " + ", ".join(_option_label(option) for option in options) + "."


def check_thread_resonance_change(
    character_sheet: CharacterSheet,
    *,
    thread: Thread | None,
    target_resonance: Resonance | None,
) -> ThreadResonanceOption:
    """Refuse a move that cannot be made; return the chosen option. Writes nothing.

    ``PerformRitualAction`` calls this before spending the rite's components and anima;
    ``change_thread_resonance`` calls it again under the thread's lock.

    Raises:
        ThreadResonanceChangeError: No thread named, a thread that is not the performer's or
            is retired, no target named (the message lists the options), a target that is
            not among the options.
    """
    if thread is None:
        raise ThreadResonanceChangeError(NAME_A_THREAD_MESSAGE)
    if thread.owner_id != character_sheet.pk or thread.retired_at is not None:
        raise ThreadResonanceChangeError(NO_THREAD_MESSAGE)
    options = thread_resonance_options(thread)
    if target_resonance is None:
        msg = f"Name the resonance to move it to: resonance=<id>. {_options_sentence(options)}"
        raise ThreadResonanceChangeError(msg)
    chosen = next((o for o in options if o.resonance.pk == target_resonance.pk), None)
    if chosen is None:
        msg = f"This thread cannot move to {target_resonance.name}. {_options_sentence(options)}"
        raise ThreadResonanceChangeError(msg)
    return chosen


@transaction.atomic
def change_thread_resonance(
    character_sheet: CharacterSheet,
    *,
    thread: Thread | None = None,
    target_resonance: Resonance | None = None,
    **_ritual_dispatch_kwargs: object,  # ritual dispatch also forwards ``ritual=``
) -> ThreadResonanceChangeResult:
    """Move ``thread`` to ``target_resonance``; merge into a live same-anchor thread there.

    Locks the thread row, re-reads its owner, retirement and points from the database (the
    identity map would answer from memory), and refuses through
    ``check_thread_resonance_change``. The points move at the option's rate
    (``scaled_thread_points``); ``level`` is unchanged.

    Raises:
        ThreadResonanceChangeError: See ``check_thread_resonance_change``.
    """
    if thread is None:
        raise ThreadResonanceChangeError(NAME_A_THREAD_MESSAGE)
    # A filter, not get(): the identity map would answer get() without the lock.
    locked = Thread.objects.select_for_update().filter(pk=thread.pk)
    row = locked.values("owner_id", "retired_at", "developed_points").first()
    if row is None or row["owner_id"] != character_sheet.pk or row["retired_at"] is not None:
        raise ThreadResonanceChangeError(NO_THREAD_MESSAGE)
    thread.developed_points = row["developed_points"]
    chosen = check_thread_resonance_change(
        character_sheet, thread=thread, target_resonance=target_resonance
    )
    from_resonance = thread.resonance
    points_before = thread.developed_points
    label = _thread_label(thread)
    survivor = _reanchor_thread(thread, chosen.resonance.pk, chosen.projected_points)
    character_sheet.character.threads.invalidate()
    merged = survivor.pk != thread.pk
    return ThreadResonanceChangeResult(
        thread_id=survivor.pk,
        from_resonance_id=from_resonance.pk,
        to_resonance_id=chosen.resonance.pk,
        points_before=points_before,
        points_moved=chosen.projected_points,
        points_after=survivor.developed_points,
        merged=merged,
        conversion_type=chosen.conversion_type,
        message=change_message(
            label,
            from_name=from_resonance.name,
            to_name=chosen.resonance.name,
            points_before=points_before,
            points_moved=chosen.projected_points,
            points_after=survivor.developed_points,
            merged=merged,
        ),
    )
