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

from world.magic.constants import RitualExecutionKind, TargetKind
from world.magic.exceptions import (
    ConversionMappingError,
    ThreadResonanceChangeError,
    UnknownOwnedThread,
    UnknownResonance,
)
from world.magic.models import Resonance, Ritual, Thread
from world.magic.models.fall_redemption import ConversionType, ResonanceConversion
from world.magic.seeds_sanctum import PURGING_RITUAL_NAME
from world.magic.services.conversion import _reanchor_thread, conversion_pair, same_anchor_threads
from world.magic.types.threads import ThreadResonanceChangeResult, ThreadResonanceOption

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

THREAD_RESONANCE_SERVICE_PATH = "world.magic.services.thread_resonance.change_thread_resonance"

NO_THREAD_MESSAGE = UnknownOwnedThread.user_message
THREAD_MOVED_MESSAGE = "That thread has just changed resonance; look at it again."
NAME_A_THREAD_MESSAGE = "Name the thread to move."
NAME_A_RESONANCE_MESSAGE = "Name the resonance to move it to."
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


def _gift_allows(thread: Thread) -> set[int] | None:
    """A GIFT thread's supported resonance pks, or None when any resonance is allowed.

    The rule ``weave_thread`` enforces: an empty supported set is unrestricted.
    """
    if thread.target_kind != TargetKind.GIFT or thread.target_gift_id is None:
        return None
    supported = {resonance.pk for resonance in thread.target_gift.cached_resonances}
    return supported or None


def thread_resonance_options(thread: Thread) -> list[ThreadResonanceOption]:
    """Every resonance ``thread`` may be moved to, with the rate and the points it would hold.

    Every other resonance of the thread's affinity (rate 1, no conversion type), and for each
    other affinity, the ``ResonanceConversion`` counterpart of the thread's resonance when an
    authored pair (``conversion_pair``) joins the two affinities. A target with no mapping or
    no pair is not offered. A thread ``thread_resonance_refusal`` holds in place has none; a
    GIFT thread is offered only its gift's supported resonances when the gift names any.
    ``merges_into_thread_id`` is the owner's live thread on the same anchor already at that
    resonance (the move would merge into it), read in one query for every option. Sorted
    for display: own affinity first, then by affinity and resonance name.
    """
    if thread_resonance_refusal(thread):
        return []
    source = thread.resonance
    points = thread.developed_points
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
    allowed = _gift_allows(thread)
    if allowed is not None:
        candidates = [c for c in candidates if c[0].pk in allowed]
    merges_into = dict(
        same_anchor_threads(thread)
        .filter(resonance_id__in=[c[0].pk for c in candidates])
        .values_list("resonance_id", "pk")
    )
    options = [
        ThreadResonanceOption(
            resonance=resonance,
            conversion_type=conversion_type,
            multiplier=multiplier,
            projected_points=scaled_thread_points(points, multiplier),
            merges_into_thread_id=merges_into.get(resonance.pk),
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
            is retired, a thread its anchor holds in place (``thread_resonance_refusal``), no
            target named (the message lists the options), a target that is not among the
            options. The messages carry no telnet syntax; the ``ritual`` command adds its
            own hint before it dispatches.
    """
    if thread is None:
        raise ThreadResonanceChangeError(NAME_A_THREAD_MESSAGE)
    if thread.owner_id != character_sheet.pk or thread.retired_at is not None:
        raise ThreadResonanceChangeError(NO_THREAD_MESSAGE)
    refusal = thread_resonance_refusal(thread)
    if refusal:
        raise ThreadResonanceChangeError(refusal)
    options = thread_resonance_options(thread)
    if target_resonance is None:
        msg = f"{NAME_A_RESONANCE_MESSAGE} {options_sentence(options)}"
        raise ThreadResonanceChangeError(msg)
    chosen = next((o for o in options if o.resonance.pk == target_resonance.pk), None)
    if chosen is None:
        msg = f"This thread cannot move to {target_resonance.name}. {options_sentence(options)}"
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
    row = locked.values("owner_id", "retired_at", "developed_points", "resonance_id").first()
    if row is None or row["owner_id"] != character_sheet.pk or row["retired_at"] is not None:
        raise ThreadResonanceChangeError(NO_THREAD_MESSAGE)
    if row["resonance_id"] != thread.resonance_id:
        # Moved by another process since this one read it: the options were worked out
        # from a resonance the thread no longer channels.
        raise ThreadResonanceChangeError(THREAD_MOVED_MESSAGE)
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
