"""Sentence enforcement — brig terms served, terminal countdown, daily sweep (#2378).

Post-verdict dispatch: :func:`schedule_sentence` routes a just-TRIED case's
``sentence_kind`` to its enforcement path — an immediate release, a brig hold
until ``sentence_ends_at``, a terminal sentence's rescue window
(``terminal_due_at``), or an apply hook for the sentences later tasks build out
(EXILE — Task 3; CONFISCATION — Task 4). :func:`sentence_sweep_tick` is the
daily cron body: it serves matured brig terms and carries out terminal
sentences whose rescue window has closed without a rescue/escape/pardon.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from world.character_sheets.types import LifecycleState
from world.justice.constants import (
    EXILE_PIN_DAYS,
    EXILE_PIN_VALUE,
    RESCUE_WINDOW_DAYS,
    CaseStatus,
    SentenceKind,
)
from world.justice.models import ExileDecree, JusticeCase, PersonaHeat

# ---------------------------------------------------------------------------
# Post-verdict dispatch
# ---------------------------------------------------------------------------


def end_captivity(case: JusticeCase) -> None:
    """Release the case's captivity, if it has one. Relocated from pipeline.py (#2378)."""
    if case.captivity is None:
        return
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.captivity.constants import CaptivityStatus  # noqa: PLC0415
    from world.captivity.services import resolve_captivity  # noqa: PLC0415

    try:
        resolve_captivity(case.captivity, status=CaptivityStatus.RELEASED)
    except (ObjectDoesNotExist, ValueError):
        return


def terminal_kind_for(case: JusticeCase) -> str:
    """EXECUTION when the lethal wall lets it through, else BANISHMENT.

    The wall (ADR-0023) is judged by :func:`world.justice.pipeline._execution_reachable`
    — imported lazily here to avoid a pipeline/sentences import cycle (pipeline
    imports this module at load time to build ``_apply_sentence``'s terminal branch).
    """
    from world.justice.pipeline import _execution_reachable  # noqa: PLC0415

    return SentenceKind.EXECUTION if _execution_reachable(case) else SentenceKind.BANISHMENT


def apply_exile(case: JusticeCase) -> None:
    """STUB — Task 3 completes EXILE sentencing (decree, heat pin, ejection, breach detection).

    For now this only releases captivity; no decree is minted (#2378 Task 3).
    """
    end_captivity(case)


def apply_confiscation(case: JusticeCase) -> None:
    """STUB — Task 4 completes CONFISCATION sentencing (property/asset seizure).

    For now this only releases captivity; nothing is seized (#2378 Task 4).
    """
    end_captivity(case)


def schedule_sentence(case: JusticeCase) -> None:
    """Post-verdict dispatcher — routes a TRIED case's sentence to its enforcement path.

    Called by :func:`world.justice.pipeline.initiate_trial` in place of the old
    unconditional captivity release: FINE/HUMILIATION release outright; BRIG_TERM
    stays held until ``sentence_ends_at``; EXECUTION/BANISHMENT stay held through
    the rescue window (``terminal_due_at``); EXILE/CONFISCATION defer to their
    apply hooks.
    """
    kind = case.sentence_kind
    if kind in (SentenceKind.FINE, SentenceKind.HUMILIATION):
        end_captivity(case)
    elif kind == SentenceKind.BRIG_TERM:
        case.sentence_ends_at = timezone.now() + timedelta(days=case.sentence_amount)
        case.save(update_fields=["sentence_ends_at"])
    elif kind in (SentenceKind.EXECUTION, SentenceKind.BANISHMENT):
        case.terminal_due_at = timezone.now() + timedelta(days=RESCUE_WINDOW_DAYS)
        case.save(update_fields=["terminal_due_at"])
    elif kind == SentenceKind.EXILE:
        apply_exile(case)
    elif kind == SentenceKind.CONFISCATION:
        apply_confiscation(case)
    else:
        # ARENA_TRIAL and any other ladder-only kind aren't wired to a default
        # dispatch path yet (Task 3/4); release rather than leave captivity stranded.
        end_captivity(case)


# ---------------------------------------------------------------------------
# Daily sweep — the cron body
# ---------------------------------------------------------------------------


def _sweep_brig_releases(now) -> int:
    """Release every HELD captivity whose BRIG_TERM has matured."""
    from world.captivity.constants import CaptivityStatus  # noqa: PLC0415
    from world.captivity.services import resolve_captivity  # noqa: PLC0415

    cases = JusticeCase.objects.filter(
        status=CaseStatus.TRIED,
        sentence_kind=SentenceKind.BRIG_TERM,
        sentence_ends_at__lte=now,
        captivity__status=CaptivityStatus.HELD,
    )
    touched = 0
    for case in cases:
        resolve_captivity(case.captivity, status=CaptivityStatus.RELEASED)
        case.sentence_ends_at = None
        case.save(update_fields=["sentence_ends_at"])
        touched += 1
    return touched


def _pin_heat_for_decree(decree: ExileDecree) -> None:
    """Minimal inline heat pin for a fresh banishment.

    Task 3 exposes the shared ``pin_heat_for_decree`` helper for EXILE decrees too;
    this inlines the same rule (floor the value, hold it through the pin window).
    """
    row, created = PersonaHeat.objects.get_or_create(
        persona=decree.persona,
        area=decree.area,
        society=decree.society,
        defaults={"value": EXILE_PIN_VALUE, "pinned_until": decree.pin_until},
    )
    if not created:
        row.value = max(row.value, EXILE_PIN_VALUE)
        row.pinned_until = decree.pin_until
        row.save(update_fields=["value", "pinned_until"])


def _carry_out_execution(case: JusticeCase, now) -> None:
    from world.captivity.constants import CaptivityStatus  # noqa: PLC0415
    from world.captivity.services import resolve_captivity  # noqa: PLC0415

    # resolve_captivity unconditionally flips the captive's lifecycle back to
    # ALIVE as part of freeing the cell — release the captivity slot FIRST,
    # then set DEAD, so the terminal state is the one that sticks.
    resolve_captivity(case.captivity, status=CaptivityStatus.RELEASED)
    sheet = case.persona.character_sheet
    if sheet is not None:
        sheet.lifecycle_state = LifecycleState.DEAD
        sheet.lifecycle_state_at = now
        sheet.save(update_fields=["lifecycle_state", "lifecycle_state_at"])
    case.terminal_carried_out_at = now
    case.save(update_fields=["terminal_carried_out_at"])


def _carry_out_banishment(case: JusticeCase, now) -> None:
    from world.captivity.constants import CaptivityStatus  # noqa: PLC0415
    from world.captivity.services import resolve_captivity  # noqa: PLC0415

    decree = ExileDecree.objects.create(
        case=case,
        persona=case.persona,
        area=case.area,
        society=case.society,
        pin_until=now + timedelta(days=EXILE_PIN_DAYS),
        ends_at=None,
    )
    _pin_heat_for_decree(decree)

    # resolve_captivity relocates the freed captive to its own default
    # destination (return_location / cell / home) as part of tearing the cell
    # down — eject to the exile destination AFTER, so the banishment ejection
    # is the move that actually sticks.
    resolve_captivity(case.captivity, status=CaptivityStatus.RELEASED)

    sheet = case.persona.character_sheet
    destination = case.area.exile_destination
    if sheet is not None and sheet.character is not None and destination is not None:
        sheet.character.move_to(destination.objectdb, quiet=True, move_type="expel")

    case.terminal_carried_out_at = now
    case.save(update_fields=["terminal_carried_out_at"])


def _sweep_terminals(now) -> int:
    """Carry out (or void) every terminal sentence whose rescue window is due."""
    from world.captivity.constants import CaptivityStatus  # noqa: PLC0415

    cases = JusticeCase.objects.filter(
        terminal_due_at__lte=now,
        terminal_carried_out_at__isnull=True,
        sentence_kind__in=[SentenceKind.EXECUTION, SentenceKind.BANISHMENT],
    )
    touched = 0
    for case in cases:
        rescued = (
            case.captivity is None
            or case.captivity.status != CaptivityStatus.HELD
            or case.status == CaseStatus.RELEASED_PARDON
        )
        if rescued:
            case.terminal_due_at = None
            case.save(update_fields=["terminal_due_at"])
            continue
        if case.sentence_kind == SentenceKind.EXECUTION:
            _carry_out_execution(case, now)
        else:
            _carry_out_banishment(case, now)
        touched += 1
    return touched


def sentence_sweep_tick() -> int:
    """Daily cron body (#2378): serve matured brig terms, carry out due terminals.

    Returns the number of cases touched (released, voided, or carried out).
    """
    now = timezone.now()
    return _sweep_brig_releases(now) + _sweep_terminals(now)
