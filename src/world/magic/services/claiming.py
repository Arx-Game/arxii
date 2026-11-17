"""Claiming kindled resonance (#5181).

A kindled deed pays part of its resonance at once and sets a share aside in
``CharacterResonance.kindled_unclaimed`` (``award_kindled_deeds``). The character collects what
waits with a claiming pose or a journal entry, whenever they like: it never expires.

``pending_claim_from`` checks what a pose or entry asked to claim before anything posts,
``claim_kindled`` collects it once the writing is down, and ``claim_lines`` are the private
lines the writer reads. The room sees only the pose.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction

from world.magic.constants import GainSource
from world.magic.exceptions import ClaimError
from world.magic.models import CharacterResonance, Resonance
from world.magic.services.resonance import grant_resonance
from world.magic.types.kindling import ClaimedResonance, PendingClaim, WaitingResonance

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.character_sheets.models import CharacterSheet

# The ledger label a claimed share carries; the verb a player reads is the affinity's own.
CLAIM_DEED_LABEL = "Claimed what a kindled deed set aside"
NOTHING_WAITING_LINE = "Nothing was waiting to be claimed."
_NOT_WAITING = "You have nothing waiting to claim in that resonance."
_BAD_IDS = "Name the resonances to claim by their ids."


def waiting_resonances(sheet: CharacterSheet) -> list[WaitingResonance]:
    """The resonances ``sheet`` has something set aside in, with how much, in resonance order.

    Reads the amounts straight from the database (``values_list`` builds no model, so the
    identity map's copy cannot be stale), then the resonances with their affinities.
    """
    amounts = dict(
        CharacterResonance.objects.filter(character_sheet=sheet, kindled_unclaimed__gt=0)
        .order_by("pk")
        .values_list("resonance_id", "kindled_unclaimed")
    )
    if not amounts:
        return []
    resonances = Resonance.objects.filter(pk__in=amounts).select_related("affinity")
    return [
        WaitingResonance(
            resonance=resonance,
            unclaimed=amounts[resonance.pk],
            verb=resonance.affinity.claim_verb,
        )
        for resonance in sorted(resonances, key=lambda r: r.name)
    ]


def unclaimed_by_resonance(sheet: CharacterSheet) -> dict[int, int]:
    """Resonance id -> what ``sheet`` has set aside there, for the "Your resonances" panel."""
    return {row.resonance.pk: row.unclaimed for row in waiting_resonances(sheet)}


def resolve_waiting_names(sheet: CharacterSheet, names: Iterable[str]) -> tuple[int, ...]:
    """The ids of the waiting resonances ``names`` name, matched without regard to case.

    Raises:
        ClaimError: a name is blank, matches no resonance the character has something waiting
            in, or nothing is waiting at all. Nothing is written.
    """
    waiting = {row.resonance.name.lower(): row.resonance.pk for row in waiting_resonances(sheet)}
    ids: list[int] = []
    for name in names:
        key = name.strip().lower()
        if not key:
            raise ClaimError(_BAD_IDS)
        if key not in waiting:
            msg = f"You have nothing waiting to claim in '{name.strip()}'."
            raise ClaimError(msg)
        if waiting[key] not in ids:
            ids.append(waiting[key])
    return tuple(ids)


def pending_claim_from(sheet: CharacterSheet, params: Any) -> PendingClaim | None:
    """The claim a pose or journal entry asked for, checked, or None when it asked for none.

    ``params`` is the action's kwargs or a serializer's validated data: ``claim`` (a flag) and
    ``claim_resonance_ids`` (optional; none or empty means everything waiting). Ids are checked
    against what the character has waiting; nothing is written.

    Raises:
        ClaimError: a named resonance has nothing waiting for the character.
    """
    from actions.kwarg_parsing import truthy_kwarg  # noqa: PLC0415

    ids = params.get("claim_resonance_ids") or ()
    if not truthy_kwarg(params.get("claim")):
        if ids:
            raise ClaimError(_BAD_IDS)
        return None
    if not ids:
        return PendingClaim()
    try:
        wanted = tuple(dict.fromkeys(int(pk) for pk in ids))
    except (TypeError, ValueError) as exc:
        raise ClaimError(_BAD_IDS) from exc
    waiting = {row.resonance.pk for row in waiting_resonances(sheet)}
    if not set(wanted) <= waiting:
        raise ClaimError(_NOT_WAITING)
    return PendingClaim(resonance_ids=wanted)


@transaction.atomic
def claim_kindled(
    sheet: CharacterSheet, resonances: Iterable[Resonance] | None = None
) -> list[ClaimedResonance]:
    """Collect what ``sheet`` has set aside to claim, all of it or only ``resonances``.

    Locks the character's rows that have something waiting, grants each one's share through
    ``grant_resonance(source=KINDLED_CLAIM)`` and zeroes the counter. Returns what the ledger
    recorded for each, which is the waiting amount after the earn rate. Nothing waiting returns
    an empty list and grants nothing.
    """
    rows = CharacterResonance.objects.select_for_update().filter(
        character_sheet=sheet, kindled_unclaimed__gt=0
    )
    if resonances is not None:
        rows = rows.filter(resonance__in=list(resonances))
    # ``values_list`` builds no model: a model fetched through the identity map keeps whatever
    # was cached on it, which an ``F()`` increment elsewhere would have left stale.
    waiting = list(rows.order_by("pk").values_list("pk", "kindled_unclaimed"))
    claimed: list[ClaimedResonance] = []
    for pk, amount in waiting:
        row = CharacterResonance.objects.get(pk=pk)
        ledger: list = []
        row = grant_resonance(
            sheet,
            row.resonance,
            amount,
            source=GainSource.KINDLED_CLAIM,
            deed_label=CLAIM_DEED_LABEL,
            ledger_out=ledger,
        )
        row.kindled_unclaimed = 0
        row.save(update_fields=["kindled_unclaimed"])
        claimed.append(
            ClaimedResonance(
                resonance=row.resonance,
                amount=ledger[-1].amount,
                verb=row.resonance.affinity.claim_verb,
            )
        )
    return claimed


def claim_line(claimed: ClaimedResonance) -> str:
    """The private line one claimed resonance reads: "You gloat. Your Ruin grows by 7."."""
    verb = claimed.verb.strip()
    opening = f"You {verb}." if verb else "You claim what was waiting."
    return f"{opening} Your {claimed.resonance.name} grows by {claimed.amount}."


def claim_lines(claimed: list[ClaimedResonance]) -> tuple[str, ...]:
    """The private lines a claim reads, one per resonance, or the nothing-waiting line."""
    if not claimed:
        return (NOTHING_WAITING_LINE,)
    return tuple(claim_line(each) for each in claimed)


def record_pending_claim(sheet: CharacterSheet, pending: PendingClaim) -> tuple[str, ...]:
    """Carry out a ``pending_claim_from`` result once its writing is down; returns the lines
    the writer reads. A claim that finds nothing waiting (a race) reads the nothing-waiting
    line; the writing stands."""
    resonances = None
    if pending.resonance_ids:
        resonances = list(Resonance.objects.filter(pk__in=pending.resonance_ids))
    return claim_lines(claim_kindled(sheet, resonances))


__all__ = [
    "CLAIM_DEED_LABEL",
    "NOTHING_WAITING_LINE",
    "claim_kindled",
    "claim_line",
    "claim_lines",
    "pending_claim_from",
    "record_pending_claim",
    "resolve_waiting_names",
    "unclaimed_by_resonance",
    "waiting_resonances",
]
