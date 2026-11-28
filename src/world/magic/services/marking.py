"""Marks (#5327): a pose or journal entry that names a resonance and points at an act.

A character gains resonance outside an authored choice only when her player marks an act her
character took (a ``RecordedAct``, written by ``award_kindled_deeds``) with the resonance it is
about, in a pose or a journal entry. Situations only suggest resonances; the mark is the
attestation. A mark may name any resonance, in her aura or not, Primal included.

``pending_mark_from`` checks what a pose or entry asked to mark before anything posts, and
raises ``MarkError``. ``record_pending_mark`` runs once the writing is saved, in one
transaction: it locks the act, takes the base amount from the act's own award, applies the
weekly table, charges the fatigue, refuses a result of 0 without consuming the act, and
otherwise grants the resonance and writes the mark onto the act.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Count, Prefetch, QuerySet, Sum
from django.utils import timezone

from world.magic.constants import GainSource
from world.magic.exceptions import MarkError
from world.magic.models import (
    KindledDeedAward,
    KindledStrengthTier,
    RecordedAct,
    RecordedActSuggestion,
    Resonance,
    ResonanceGrant,
    WeeklyMarkReturn,
)
from world.magic.services.gain_fatigue import (
    charge_gain_fatigue,
    gain_fatigue_payer,
    refusal_line,
    shrink_reason,
    stay_small_sentence,
)
from world.magic.services.resonance import grant_resonance
from world.magic.services.resonance_checks import (
    FULL_WORTH_PERCENT,
    act_stat,
    gain_bonus_clause,
)
from world.magic.types.marking import (
    GainFatigueCharge,
    MarkResult,
    PendingMark,
    WeeklyStanding,
)
from world.scenes.interaction_services import notify_interaction_changed

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.journals.models import JournalEntry
    from world.scenes.models import Interaction

_UNKNOWN_RESONANCE = "That resonance does not exist. Choose one from the list."
_NO_ACT = "That act is not on your list of acts. Choose one from the list of acts you can mark."
_NO_RESONANCE = "Name the resonance this act is about, as well as the act."
_ALREADY_MARKED = "You have already marked that act, so it cannot pay again. Choose another act."
_TOO_OLD = (
    "That act is too old to mark any more. Choose a more recent act, or take a new action "
    "and mark that."
)
_WORTHLESS = (
    "That act is no longer worth anything, so marking it would pay nothing. Choose another act."
)
_WEEK_SPENT = (
    "Your marks this week have already paid all they will, so this one would pay nothing. "
    "The act stays on your list: mark it next week, when marks pay in full again."
)
_EPHEMERAL = (
    "This scene is ephemeral and stores nothing, so a mark here pays nothing. "
    "Mark the act later, in a pose in another scene or from a journal entry."
)
_POSE_HAS_MARK = (
    "This pose already marks an act, and a pose marks only one. Mark the next act in "
    "another pose or in a journal entry."
)
_ENTRY_HAS_MARK = (
    "This journal entry already marks an act, and an entry marks only one. Mark the next "
    "act in another entry."
)
_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
)


def _whole_id(raw: Any, message: str) -> int:
    """``raw`` as an id, or a ``MarkError`` saying ``message`` (a bool is never an id)."""
    if isinstance(raw, bool):
        raise MarkError(message)
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise MarkError(message) from exc


def pending_mark_from(sheet: CharacterSheet, params: Any) -> PendingMark | None:
    """The mark a pose or journal entry asked for, checked, or None when it asked for none.

    ``params`` is the action's kwargs or a serializer's validated data: ``reach_act_id`` (the
    act) and ``reach_resonance_id`` (the resonance). With no act there is no mark (the
    resonance alone is a bare reach, ``pending_reach_from``). The act must be one of
    ``sheet``'s own, unmarked and inside ``KindlingConfig.recorded_act_days``; any existing
    resonance is valid, in her aura or not. Nothing is written.

    Raises:
        MarkError: the act or the resonance is not valid, or no resonance is named.
    """
    raw_act = params.get("reach_act_id")
    if raw_act is None or raw_act == "":
        return None
    act_id = _whole_id(raw_act, _NO_ACT)
    raw_resonance = params.get("reach_resonance_id")
    if raw_resonance is None or raw_resonance == "":
        raise MarkError(_NO_RESONANCE)
    resonance_id = _whole_id(raw_resonance, _UNKNOWN_RESONANCE)
    row = (
        RecordedAct.objects.filter(pk=act_id, character_sheet=sheet)
        .values("marked_grant_id", "created_at")
        .first()
    )
    if row is None:
        raise MarkError(_NO_ACT)
    if row["marked_grant_id"] is not None:
        raise MarkError(_ALREADY_MARKED)
    if row["created_at"] < timezone.now() - timedelta(days=_recorded_act_days()):
        raise MarkError(_TOO_OLD)
    if not Resonance.objects.filter(pk=resonance_id).exists():
        raise MarkError(_UNKNOWN_RESONANCE)
    return PendingMark(act_id=act_id, resonance_id=resonance_id)


def _recorded_act_days() -> int:
    from world.magic.services.kindling import get_kindling_config  # noqa: PLC0415

    return get_kindling_config().recorded_act_days


def pointable_acts_queryset() -> QuerySet[RecordedAct]:
    """Every unmarked act inside ``KindlingConfig.recorded_act_days``, newest first, each with
    its suggestions (``cached_suggestions``, strongest first) fetched with it.

    The one definition of what a mark can still point at: the recorded-acts endpoint and
    telnet ``acts`` both start from it, then narrow to a character.
    """
    window_start = timezone.now() - timedelta(days=_recorded_act_days())
    return (
        RecordedAct.objects.filter(marked_grant__isnull=True, created_at__gte=window_start)
        .prefetch_related(
            Prefetch(
                "suggestions",
                queryset=RecordedActSuggestion.objects.select_related("resonance").order_by(
                    "-strength__rank", "resonance__name"
                ),
                to_attr="cached_suggestions",
            )
        )
        .order_by("-created_at", "-pk")
    )


def pointable_acts(sheet: CharacterSheet) -> list[RecordedAct]:
    """``sheet``'s pointable acts, newest first."""
    return list(pointable_acts_queryset().filter(character_sheet=sheet))


def pointable_acts_page(sheet: CharacterSheet, limit: int) -> tuple[list[RecordedAct], int]:
    """The newest ``limit`` of ``sheet``'s pointable acts, and how many older ones are left out.

    Telnet ``acts`` prints each act's own id, and ``pose/reach <resonance>:<id>=`` marks the act
    with that id. An id never shifts when a newer act lands, as a place in the list would.
    """
    queryset = pointable_acts_queryset().filter(character_sheet=sheet)
    shown = list(queryset[:limit])
    older = queryset.count() - len(shown) if len(shown) == limit else 0
    return shown, older


def weekly_percent_paid(sheet: CharacterSheet) -> WeeklyStanding:
    """Where ``sheet`` stands on the weekly table of marks, before the mark in hand.

    Counts this game week's ``MARKED_ACT`` grants that nobody undid. The row of
    ``WeeklyMarkReturn`` with the greatest ``gained_at_least`` at or below what they paid sets
    the percent; no row applies means 100. Authored choices and endorsements are never counted.
    """
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    week = get_current_game_week()
    totals = ResonanceGrant.objects.filter(
        character_sheet=sheet,
        source=GainSource.MARKED_ACT,
        nullified_at__isnull=True,
        granted_at__gte=week.started_at,
    ).aggregate(gained=Sum("amount"), marks=Count("pk"))
    gained = totals["gained"] or 0
    row = (
        WeeklyMarkReturn.objects.filter(gained_at_least__lte=gained)
        .order_by("-gained_at_least")
        .first()
    )
    return WeeklyStanding(
        gained=gained,
        marks=totals["marks"],
        percent_paid=FULL_WORTH_PERCENT if row is None else row.percent_paid,
    )


def mark_base_amount(act: RecordedAct, resonance: Resonance) -> int | None:
    """What marking ``act`` with ``resonance`` is worth before the weekly table and fatigue.

    The act's ``KindledDeedAward`` for its result tier times the earn share of the strength a
    situation reached for this resonance, or of the lowest strength when none suggested it,
    rounded down and at least 1. None when the tier has no award row any more.
    """
    award = KindledDeedAward.objects.filter(outcome_tier=act.outcome).first()
    if award is None:
        return None
    suggestion = act.suggestions.filter(resonance=resonance).select_related("strength").first()
    strength = (
        suggestion.strength
        if suggestion is not None
        else KindledStrengthTier.objects.order_by("rank").first()
    )
    share = strength.earn_percent if strength is not None else 0
    return max(1, award.amount * share // 100)


@transaction.atomic
def record_pending_mark(
    sheet: CharacterSheet,
    pending: PendingMark,
    *,
    interaction: Interaction | None = None,
    journal_entry: JournalEntry | None = None,
) -> MarkResult:
    """Pay a ``pending_mark_from`` result once the pose or journal entry that carried it is saved.

    Exactly one of ``interaction`` and ``journal_entry`` is the writing; with neither (a pose
    in an ephemeral scene stores none) nothing pays, the act stays pointable and the line says
    so. Otherwise: lock the act, take ``mark_base_amount``, apply the weekly table, charge the
    fatigue (the amount shrinks to what the payer can still pay), then ``grant_resonance`` as
    ``MARKED_ACT`` with the act's own stat and label, and write the grant and the writing onto
    the act, all in this transaction. The returned line is what the writer reads.

    Raises:
        MarkError: the act is gone, not hers or already marked, or the mark would pay nothing
            (the weekly table or the payer's room). Nothing is written and the act is not
            consumed.
    """
    if interaction is None and journal_entry is None:
        return MarkResult(line=_EPHEMERAL)
    locked = list(
        RecordedAct.objects.select_for_update()
        .filter(pk=pending.act_id, character_sheet=sheet)
        .values_list("marked_grant_id", flat=True)
    )
    if not locked:
        raise MarkError(_NO_ACT)
    if locked[0] is not None:
        raise MarkError(_ALREADY_MARKED)
    # One mark per writing: refused cleanly here, before anything is paid.
    if (
        interaction is not None
        and RecordedAct.objects.filter(marked_interaction=interaction).exists()
    ):
        raise MarkError(_POSE_HAS_MARK)
    if (
        journal_entry is not None
        and RecordedAct.objects.filter(marked_journal_entry=journal_entry).exists()
    ):
        raise MarkError(_ENTRY_HAS_MARK)
    act = RecordedAct.objects.select_related("outcome", "check_type", "target_sheet").get(
        pk=pending.act_id
    )
    resonance = Resonance.objects.select_related("affinity").get(pk=pending.resonance_id)

    base = mark_base_amount(act, resonance)
    if base is None:
        raise MarkError(_WORTHLESS)
    standing = weekly_percent_paid(sheet)
    # A step above 0 percent pays at least 1; only a 0 percent step refuses the mark.
    amount = max(1, base * standing.percent_paid // 100) if standing.percent_paid > 0 else 0
    if amount <= 0:
        raise MarkError(_WEEK_SPENT)
    charge = charge_gain_fatigue(
        sheet,
        gain_fatigue_payer(sheet, resonance, act.target_sheet),
        resonance,
        act.fatigue_category,
        amount,
    )
    if charge.refused:
        raise MarkError(refusal_line(charge, sheet, resonance))

    ledger: list[ResonanceGrant] = []
    grant_resonance(
        sheet,
        resonance,
        charge.amount,
        source=GainSource.MARKED_ACT,
        act_stat=act_stat(act.check_type) if act.check_type is not None else None,
        deed_label=act.label,
        ledger_out=ledger,
    )
    grant = ledger[-1]
    act.marked_grant = grant
    act.marked_interaction = interaction
    act.marked_journal_entry = journal_entry
    act.save(update_fields=["marked_grant", "marked_interaction", "marked_journal_entry"])
    # What situations suggested is dead weight once the act is marked.
    RecordedActSuggestion.objects.filter(act=act).delete()
    del act.cached_suggestions
    if interaction is not None:
        notify_interaction_changed(interaction)
    return MarkResult(
        line=_paid_line(sheet, resonance, grant, standing, charge, asked=amount), grant=grant
    )


def _full_size(resonance: Resonance, asked: int, bonus_percent: int) -> int:
    """What a gain of ``asked`` would have been after the affinity's earn rate and the bonus
    percent, the two steps ``grant_resonance`` applies, so a shrunk gain can say what it was
    cut from."""
    scaled = max(asked * resonance.affinity.earn_rate_percent // 100, 1)
    return scaled + scaled * bonus_percent // 100


def _mark_ordinal(number: int) -> str:
    """ "your fifth mark" up to the tenth, then "mark number 11"."""
    if number <= len(_ORDINALS):
        return f"your {_ORDINALS[number - 1]} mark"
    return f"mark number {number}"


def _paid_line(  # noqa: PLR0913 - the sheet, what was marked, what it paid and why
    sheet: CharacterSheet,
    resonance: Resonance,
    grant: ResonanceGrant,
    standing: WeeklyStanding,
    charge: GainFatigueCharge,
    *,
    asked: int,
) -> str:
    """The private line a mark's writer reads, in the order the approved design shows: the
    affinity's verb, what grew (and that she is wearier, when she paid), why it was cut by
    fatigue, why it was cut by the week, then the bonus check."""
    verb = resonance.affinity.claim_verb.strip()
    grew = f"Your {resonance.name} grows by {grant.amount}"
    parts = [f"You {verb}." if verb else ""]
    if charge.shrunk:
        full = _full_size(resonance, asked, grant.bonus_percent)
        grew += f" instead of {full}, {shrink_reason(charge, sheet)}"
    if charge.payer is not None and charge.payer.pk == sheet.pk and charge.charged > 0:
        grew += ", and you are wearier"
    parts.append(f"{grew}.")
    if charge.shrunk:
        parts.append(stay_small_sentence(charge, sheet))
    if standing.percent_paid < FULL_WORTH_PERCENT:
        parts.append(
            f"This is {_mark_ordinal(standing.marks + 1)} this week, so it paid "
            f"{standing.percent_paid} percent. Marks pay in full again next week."
        )
    parts.append(gain_bonus_clause(resonance.affinity, grant.bonus_percent))
    return " ".join(part for part in parts if part)


__all__ = [
    "mark_base_amount",
    "pending_mark_from",
    "pointable_acts",
    "pointable_acts_page",
    "pointable_acts_queryset",
    "record_pending_mark",
    "weekly_percent_paid",
]
