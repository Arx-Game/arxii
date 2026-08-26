"""Sentence enforcement — brig terms served, terminal countdown, daily sweep (#2378).

Post-verdict dispatch: :func:`schedule_sentence` routes a just-TRIED case's
``sentence_kind`` to its enforcement path — an immediate release (with a
prestige-hit apply hook for HUMILIATION, Task 5), a brig hold until
``sentence_ends_at``, a terminal sentence's rescue window (``terminal_due_at``),
or an apply hook for the sentences later tasks build out (EXILE — Task 3;
CONFISCATION — Task 4). :func:`sentence_sweep_tick` is the daily cron body: it
serves matured brig terms and carries out terminal sentences whose rescue
window has closed without a rescue/escape/pardon. :func:`active_public_marks`
(Task 5) derives the public record of standing consequences in an area — no
stored row, term-limited by arithmetic on read.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from world.character_sheets.types import LifecycleState
from world.justice.constants import (
    EXILE_PIN_DAYS,
    EXILE_PIN_VALUE,
    FINE_COPPERS_PER_WEIGHT,
    HUMILIATION_PRESTIGE_HIT,
    HUMILIATION_TERM_DAYS,
    RESCUE_WINDOW_DAYS,
    CaseStatus,
    SentenceKind,
)
from world.justice.models import ExileDecree, JusticeCase, PersonaHeat
from world.justice.notifications import notify_brig_visitation, notify_verdict
from world.justice.types import PublicMark

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.scenes.models import Persona

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


def pin_heat_for_decree(decree: ExileDecree) -> PersonaHeat:
    """Floor a persona's heat at ``EXILE_PIN_VALUE`` and hold it through the pin window.

    Shared by EXILE sentencing (:func:`apply_exile`) and terminal BANISHMENT
    (:func:`_carry_out_banishment`) — one pin implementation, not two.
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
    return row


def eject(case: JusticeCase) -> bool:
    """Cast the case's persona out to the area's ``exile_destination``, if set.

    Sheet/character null-safe: a bodiless persona or an area with no
    ``exile_destination`` configured no-ops (nothing to move — logged and
    skipped by the caller's own best-effort framing). Messages the room
    BEFORE moving. Returns whether the move happened.
    """
    sheet = case.persona.character_sheet
    destination = case.area.exile_destination
    if sheet is None or sheet.character is None or destination is None:
        return False
    character = sheet.character
    location = character.location
    if location is not None:
        # PLACEHOLDER copy (spec #2378 §5) — neutral wording pending a design pass.
        location.msg_contents(
            f"{case.persona.name} is seized by the guard and cast out of {case.area.name}."
        )
    character.move_to(destination.objectdb, quiet=True, move_type="expel")
    return True


def is_magically_concealed(persona: Persona) -> bool:  # noqa: ARG001 — seam, wired later
    """Seam for the ratified magic exception (spec #2378 §5): magical concealment
    (invisibility, shapechange) bypasses the mundane exile gauntlet absent magical
    detection. The magical-detection taxonomy is TehomCD's substrate; wire this
    to it when it exists. Candidate substrate: resolve_security_check(SNEAK) (#3301,
    zero callers). Always False today — ``persona`` is part of the seam's
    contract even though this stub body doesn't consult it yet.
    """
    return False


def apply_exile(case: JusticeCase) -> ExileDecree:
    """EXILE sentencing (#2378 Task 3): decree, heat pin, ejection, captivity release.

    Captivity is released BEFORE the ejection move — ``resolve_captivity``
    unconditionally relocates the freed captive to its own default destination
    as part of tearing the cell down, so ejecting first would have that
    relocation clobber the exile destination. Mirrors
    :func:`_carry_out_banishment`'s ordering.
    """
    now = timezone.now()
    decree = ExileDecree.objects.create(
        case=case,
        persona=case.persona,
        area=case.area,
        society=case.society,
        pin_until=now + timedelta(days=EXILE_PIN_DAYS),
        ends_at=now + timedelta(days=case.sentence_amount),
    )
    pin_heat_for_decree(decree)
    end_captivity(case)
    eject(case)
    case.sentence_ends_at = decree.ends_at
    case.save(update_fields=["sentence_ends_at"])
    return decree


def apply_confiscation(case: JusticeCase) -> None:
    """CONFISCATION sentencing (#2378 Task 4): seize carried goods into the area's brig.

    Recoverable, not destroyed (spec #2378 §8): items move into the area's Brig
    room's inventory rather than being deleted, so a later pardon or rescue can
    hand them back. PLACEHOLDER rule: seizes the accused's WHOLE carried
    inventory wholesale — no worn/equipped filtering (a later content pass can
    split "seizable" from "kept on the body"). Falls back to a double-rate fine
    (:func:`_collect_fine_double`) when the area has no Brig to hold the goods,
    or the accused has no body to search (a bodiless persona / NPC with no
    character).
    """
    from world.room_features.brig_services import find_brig_for_area  # noqa: PLC0415

    storage = find_brig_for_area(case.area)
    sheet = case.persona.character_sheet
    character = sheet.character if sheet is not None else None
    if storage is None or character is None:
        _collect_fine_double(case)
        end_captivity(case)
        return
    for obj in list(character.contents):
        obj.move_to(storage.objectdb, quiet=True)
    end_captivity(case)


def _collect_fine_double(case: JusticeCase) -> None:
    """Fallback fine for confiscation when there's nowhere to put seized goods.

    Mirrors :func:`world.justice.pipeline._collect_fine`'s debit shape, but at
    double the base coppers-per-weight rate (spec #2378 §8) — losing your goods
    outright costs more than the coin they'd have fetched. Independent of
    ``case.sentence_amount`` (CONFISCATION carries no numeric term of its own).
    """
    from world.currency.services import get_or_create_purse  # noqa: PLC0415

    sheet = case.persona.character_sheet
    if sheet is None:
        return
    purse = get_or_create_purse(sheet)
    amount = case.prosecution_weight * FINE_COPPERS_PER_WEIGHT * 2
    debit = min(purse.balance, amount)
    purse.balance -= debit
    purse.save(update_fields=["balance"])


def apply_humiliation(case: JusticeCase) -> None:
    """HUMILIATION sentencing (#2378 Task 5): a deed-prestige hit, clamped at zero.

    Called from :func:`schedule_sentence` BEFORE the sentence's outright release.
    NO prose beyond neutral procedural strings anywhere in this path — the
    persona's own record and the public feed both say only that they were
    "sentenced by the magistrates," never what the humiliation was. Dan
    (Apostate) authors the real humiliation copy personally; this hook is
    mechanics-only.
    """
    from world.societies.renown import award_deed_prestige  # noqa: PLC0415

    persona = case.persona
    hit = min(HUMILIATION_PRESTIGE_HIT, max(0, persona.prestige_from_deeds))
    if hit:
        award_deed_prestige(persona, -hit)


def active_public_marks(*, area: Area, now: datetime | None = None) -> list[PublicMark]:
    """The public record standing against personas in ``area`` (#2378 Task 5).

    Derived on read from three sources, term-limited by arithmetic rather than
    a stored/expiring row (spec #2378 §4):

    - **Humiliations** — cases sentenced HUMILIATION whose ``resolved_at`` is
      still inside ``HUMILIATION_TERM_DAYS``; ``until`` is the day the mark ages
      off.
    - **Exiles/banishments** — active ``ExileDecree`` rows (not lifted, and
      either permanent or not yet expired); ``until=None`` for a permanent
      banishment, else the decree's ``ends_at``.
    - **Pending terminals** — the visible countdown (spec #2378 §9): cases with
      a ``terminal_due_at`` still in the future that haven't been carried out.

    ``select_related("persona")`` on every source — no queries in the loops
    that build the dataclass rows.
    """
    now = now or timezone.now()
    area_name = area.name
    marks: list[PublicMark] = []

    humiliation_cases = JusticeCase.objects.filter(
        area=area,
        sentence_kind=SentenceKind.HUMILIATION,
        resolved_at__gt=now - timedelta(days=HUMILIATION_TERM_DAYS),
    ).select_related("persona")
    marks.extend(
        PublicMark(
            kind=SentenceKind.HUMILIATION,
            persona_name=case.persona.name,
            area_name=area_name,
            until=case.resolved_at + timedelta(days=HUMILIATION_TERM_DAYS),
        )
        for case in humiliation_cases
    )

    decrees = (
        ExileDecree.objects.filter(area=area, lifted_at__isnull=True)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .select_related("persona")
    )
    marks.extend(
        PublicMark(
            kind="banishment" if decree.ends_at is None else "exile",
            persona_name=decree.persona.name,
            area_name=area_name,
            until=decree.ends_at,
        )
        for decree in decrees
    )

    terminal_cases = JusticeCase.objects.filter(
        area=area,
        terminal_due_at__gt=now,
        terminal_carried_out_at__isnull=True,
    ).select_related("persona")
    marks.extend(
        PublicMark(
            kind=case.sentence_kind,
            persona_name=case.persona.name,
            area_name=area_name,
            until=case.terminal_due_at,
        )
        for case in terminal_cases
    )

    return marks


def schedule_sentence(case: JusticeCase) -> None:
    """Post-verdict dispatcher — routes a TRIED case's sentence to its enforcement path.

    Called by :func:`world.justice.pipeline.initiate_trial` in place of the old
    unconditional captivity release: FINE/HUMILIATION release outright; BRIG_TERM
    stays held until ``sentence_ends_at``; EXECUTION/BANISHMENT stay held through
    the rescue window (``terminal_due_at``); EXILE/CONFISCATION defer to their
    apply hooks.
    """
    kind = case.sentence_kind
    if kind == SentenceKind.FINE:
        end_captivity(case)
    elif kind == SentenceKind.HUMILIATION:
        apply_humiliation(case)
        end_captivity(case)
    elif kind == SentenceKind.BRIG_TERM:
        case.sentence_ends_at = timezone.now() + timedelta(days=case.sentence_amount)
        case.save(update_fields=["sentence_ends_at"])
        _notify_brig_visitation(case)
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


def _notify_brig_visitation(case: JusticeCase) -> None:
    """Best-effort brig-visitation advert — never breaks sentence dispatch.

    Mirrors :func:`world.societies.renown.fire_renown_award`'s notify guard (#2378
    Task 6): the advert is a UX nicety, the sentence write is the source of truth.
    """
    try:
        notify_brig_visitation(case)
    except Exception:  # best-effort notify; never break sentence dispatch
        logger.exception("justice.notify_brig_visitation failed for case %s", case.pk)


def _notify_verdict(case: JusticeCase) -> None:
    """Best-effort verdict re-notification for the sweep's carried-out/voided paths.

    Mirrors :func:`world.societies.renown.fire_renown_award`'s notify guard (#2378
    Task 6): the notification is a UX nicety, the terminal-sentence write is the
    source of truth.
    """
    try:
        notify_verdict(case)
    except Exception:  # best-effort notify; never break the sweep
        logger.exception("justice.notify_verdict failed for case %s", case.pk)


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
    _notify_verdict(case)


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
    pin_heat_for_decree(decree)

    # resolve_captivity relocates the freed captive to its own default
    # destination (return_location / cell / home) as part of tearing the cell
    # down — eject to the exile destination AFTER, so the banishment ejection
    # is the move that actually sticks.
    resolve_captivity(case.captivity, status=CaptivityStatus.RELEASED)
    eject(case)

    case.terminal_carried_out_at = now
    case.save(update_fields=["terminal_carried_out_at"])
    _notify_verdict(case)


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
            _notify_verdict(case)
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
