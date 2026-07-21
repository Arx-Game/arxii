"""The automated justice pipeline (#2378) — guards, arrest, trial, sentence.

Players are never the enforcement side (ratified 2026-07-14): guard pressure
is event-driven rolls against ACTIVE public play (never offline, never in
private rooms), arrest lands in captivity, the trial waits on the captive to
initiate, and helpers can only help. The lethal wall (ADR-0023) holds: PC
execution needs the target's OOC opt-in AND an exhausted case — never one roll.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from django.utils import timezone

from world.justice.constants import (
    ADVOCACY_CHECK_TYPE_NAME,
    ADVOCACY_WEIGHT_PER_LEVEL,
    BRIG_DAYS_PER_WEIGHT,
    EVASION_BOTCH_LEVEL,
    EVASION_CHECK_TYPE_NAME,
    EVASION_ESCAPE_HEAT_BUMP,
    EVIDENCE_TAMPERING_CRIME_SLUG,
    EVIDENCE_TAMPERING_SCALE,
    EVIDENCE_WEIGHT_MANUFACTURED_MAX,
    EVIDENCE_WEIGHT_REAL,
    EXECUTION_MIN_FAILED_OUTS,
    FINE_COPPERS_PER_WEIGHT,
    GUARD_ENCOUNTER_PCT_NPC_TRANSACTION,
    GUARD_ENCOUNTER_PCT_PUBLIC_INTERACTION,
    GUARD_ENCOUNTER_PCT_ROOM_ARRIVAL,
    HUNTED_VALUE_FLOOR,
    MAX_VALUE_FLOOR,
    RELEASE_THRESHOLD_FACTOR,
    VERDICT_ACQUIT_MARGIN,
    VERDICT_LESSER_MARGIN,
    WANTED_VALUE_FLOOR,
    CaseStatus,
    EncounterOutcome,
    GuardTrigger,
    SentenceKind,
    Verdict,
)
from world.justice.models import (
    CrimeKind,
    ExculpatoryEvidence,
    GuardEncounter,
    JusticeCase,
    PersonaHeat,
)
from world.justice.services import enforcing_society_for

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.scenes.models import Persona


def public_room_profile(location):
    """The location's RoomProfile when it is a public room, else None."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    if location is None:
        return None
    try:
        profile = location.room_profile
    except (AttributeError, ObjectDoesNotExist):
        return None
    return profile if profile.is_public else None


class JusticePipelineError(Exception):
    """A pipeline rule was violated. Carries a safe user message."""

    def __init__(self, msg: str, *, user_message: str) -> None:
        super().__init__(msg)
        self.user_message = user_message


_TRIGGER_PCT = {
    GuardTrigger.NPC_TRANSACTION: GUARD_ENCOUNTER_PCT_NPC_TRANSACTION,
    GuardTrigger.PUBLIC_INTERACTION: GUARD_ENCOUNTER_PCT_PUBLIC_INTERACTION,
    GuardTrigger.ROOM_ARRIVAL: GUARD_ENCOUNTER_PCT_ROOM_ARRIVAL,
}

# The tier floor each trigger kind requires (the ratified ladder).
_TRIGGER_FLOOR = {
    GuardTrigger.NPC_TRANSACTION: WANTED_VALUE_FLOOR,
    GuardTrigger.PUBLIC_INTERACTION: HUNTED_VALUE_FLOOR,
    GuardTrigger.ROOM_ARRIVAL: MAX_VALUE_FLOOR,
}


def heat_value_for(persona: Persona, area: Area) -> int:
    return sum(row.value for row in PersonaHeat.objects.filter(persona=persona, area=area))


def maybe_guard_encounter(
    persona: Persona,
    area: Area | None,
    trigger: str,
    *,
    rng: random.Random | None = None,
) -> GuardEncounter | None:
    """Roll the trigger ladder. Only fires against active play in public space.

    Below each trigger's tier floor: nothing. An already-open encounter or an
    open case suppresses new pressure (they're already caught or cornered).
    """
    if area is None:
        return None
    if heat_value_for(persona, area) < _TRIGGER_FLOOR.get(trigger, MAX_VALUE_FLOOR):
        return None
    if GuardEncounter.objects.filter(persona=persona, area=area, resolved_at__isnull=True).exists():
        return None
    if JusticeCase.objects.filter(
        persona=persona, area=area, status=CaseStatus.AWAITING_TRIAL
    ).exists():
        return None
    rng = rng or random
    if rng.random() * 100 >= _TRIGGER_PCT.get(trigger, 0):
        return None
    return GuardEncounter.objects.create(persona=persona, area=area, trigger=trigger)


def _resolve_evasion_level(encounter: GuardEncounter, check_level: int | None) -> int:
    """Determine the evasion check success level for an encounter.

    ``check_level`` injects a band for tests; otherwise the evasion check type
    rolls (degrading to a plain escape when unseeded — pressure never lands
    without the content in place).
    """
    if check_level is not None:
        return check_level
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    sheet = encounter.persona.character_sheet
    character = sheet.character if sheet is not None else None
    check_type = CheckType.objects.filter(name=EVASION_CHECK_TYPE_NAME).first()
    if character is None or check_type is None:
        return 1  # unseeded world / bodiless persona: escape clean
    result = perform_check(character, check_type)
    return result.outcome.success_level if result.outcome else 0


def _apply_encounter_outcome(encounter: GuardEncounter, level: int) -> None:
    """Set the encounter outcome based on the evasion level and bump heat if seen."""
    if level > 0:
        encounter.outcome = EncounterOutcome.ESCAPED
    elif level > EVASION_BOTCH_LEVEL:
        encounter.outcome = EncounterOutcome.ESCAPED_SEEN
        _bump_heat_for_seen_escape(encounter)
    else:
        encounter.outcome = EncounterOutcome.CAPTURED


def _bump_heat_for_seen_escape(encounter: GuardEncounter) -> None:
    """Increase heat on the persona's top heat row for the encounter area."""
    row = (
        PersonaHeat.objects.filter(persona=encounter.persona, area=encounter.area)
        .order_by("-value")
        .first()
    )
    if row is not None:
        row.value += EVASION_ESCAPE_HEAT_BUMP
        row.save(update_fields=["value"])


def resolve_guard_encounter(
    encounter: GuardEncounter, *, check_level: int | None = None
) -> GuardEncounter:
    """Evasion check: slip away clean / seen (heat bump) / captured (botch too).

    ``check_level`` injects a band for tests; otherwise the evasion check type
    rolls (degrading to a plain escape when unseeded — pressure never lands
    without the content in place).
    """
    if encounter.resolved_at is not None:
        return encounter

    level = _resolve_evasion_level(encounter, check_level)
    _apply_encounter_outcome(encounter, level)
    encounter.resolved_at = timezone.now()
    encounter.save(update_fields=["outcome", "resolved_at"])

    if encounter.outcome == EncounterOutcome.CAPTURED:
        _open_case_for_capture(encounter)
    return encounter


def _open_case_for_capture(encounter: GuardEncounter) -> JusticeCase | None:
    society = enforcing_society_for(encounter.area)
    if society is None:
        return None
    weight = heat_value_for(encounter.persona, encounter.area)
    case = JusticeCase.objects.create(
        persona=encounter.persona,
        area=encounter.area,
        society=society,
        prosecution_weight=weight,
    )
    case.captivity = _take_into_custody(encounter, society)
    if case.captivity is not None:
        case.save(update_fields=["captivity"])
    return case


def _take_into_custody(encounter: GuardEncounter, society):
    """Brig the captive via the existing captivity machinery. Best-effort:
    a bodiless persona (no character) stays uncaptured but the case opens."""
    from world.captivity.services import capture_character  # noqa: PLC0415
    from world.societies.models import Organization  # noqa: PLC0415

    sheet = encounter.persona.character_sheet
    if sheet is None or sheet.character is None:
        return None
    captor = Organization.objects.filter(society=society).first()
    from world.captivity.services import AlreadyCapturedError  # noqa: PLC0415

    try:
        return capture_character(captive=sheet, captor_organization=captor)
    except AlreadyCapturedError:
        return None


# ---------------------------------------------------------------------------
# Exculpatory evidence — helpers can only help
# ---------------------------------------------------------------------------


def release_threshold(case: JusticeCase) -> int:
    return max(10, case.prosecution_weight // RELEASE_THRESHOLD_FACTOR)


def exculpatory_total(case: JusticeCase) -> int:
    return sum(row.weight for row in ExculpatoryEvidence.objects.filter(case=case, exposed=False))


def submit_exculpatory(
    case: JusticeCase,
    submitter: Persona,
    *,
    manufactured: bool = False,
    check_level: int | None = None,
) -> ExculpatoryEvidence:
    """Add evidence FOR release. Past the threshold, the captive walks — no trial.

    Real evidence carries fixed weight. Manufactured evidence is check-banded
    (``check_level`` injectable) and risks later exposure — on the SUBMITTER.
    """
    if case.status != CaseStatus.AWAITING_TRIAL:
        msg = f"case {case.pk} is not awaiting trial"
        raise JusticePipelineError(msg, user_message="That case is closed.")
    if manufactured:
        level = check_level if check_level is not None else 0
        weight = max(0, min(EVIDENCE_WEIGHT_MANUFACTURED_MAX, (level + 1) * 4))
    else:
        weight = EVIDENCE_WEIGHT_REAL
    evidence = ExculpatoryEvidence.objects.create(
        case=case, submitter_persona=submitter, weight=weight, manufactured=manufactured
    )
    if exculpatory_total(case) >= release_threshold(case):
        _release(case, CaseStatus.RELEASED_EVIDENCE)
    return evidence


def expose_exculpatory(evidence: ExculpatoryEvidence) -> None:
    """Manufactured evidence unmasked: the SUBMITTER answers for it.

    Never worsens the accused's case (a completed release stands).
    """
    if evidence.exposed or not evidence.manufactured:
        return
    evidence.exposed = True
    evidence.save(update_fields=["exposed"])
    from world.justice.services import accrue_heat  # noqa: PLC0415

    kind, _ = CrimeKind.objects.get_or_create(
        slug=EVIDENCE_TAMPERING_CRIME_SLUG, defaults={"name": "Evidence Tampering"}
    )
    accrue_heat(
        persona=evidence.submitter_persona,
        crime_kind=kind,
        area=evidence.case.area,
        scale=EVIDENCE_TAMPERING_SCALE,
    )


def _release(case: JusticeCase, status: str) -> None:
    case.status = status
    case.resolved_at = timezone.now()
    case.save(update_fields=["status", "resolved_at"])
    _end_captivity(case)


def _end_captivity(case: JusticeCase) -> None:
    if case.captivity is None:
        return
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.captivity.constants import CaptivityStatus  # noqa: PLC0415
    from world.captivity.services import resolve_captivity  # noqa: PLC0415

    try:
        resolve_captivity(case.captivity, status=CaptivityStatus.RELEASED)
    except (ObjectDoesNotExist, ValueError):
        return


# ---------------------------------------------------------------------------
# Trial — captive-initiated, defense-only agency
# ---------------------------------------------------------------------------


def initiate_trial(
    case: JusticeCase,
    initiator: Persona,
    helpers: list[Persona] | None = None,
    *,
    check_levels: list[int] | None = None,
) -> JusticeCase:
    """The captive chooses their moment. Nobody prosecutes — the evidence does.

    Defense weight = argument checks (accused + helpers) + surviving
    exculpatory submissions. Verdict bands map the margin against the
    prosecution weight; sentence scales with that weight.
    """
    if case.status != CaseStatus.AWAITING_TRIAL:
        msg = f"case {case.pk} is not awaiting trial"
        raise JusticePipelineError(msg, user_message="That case is closed.")
    if initiator.pk != case.persona_id:
        msg = f"persona {initiator.pk} is not the accused on case {case.pk}"
        raise JusticePipelineError(msg, user_message="Only the accused may call for their trial.")

    participants: list[Persona] = [case.persona, *(helpers or [])]
    levels = check_levels if check_levels is not None else _argument_levels(participants)
    defense = sum(max(0, level) * ADVOCACY_WEIGHT_PER_LEVEL for level in levels)
    defense += exculpatory_total(case)
    margin = defense - case.prosecution_weight

    if margin >= VERDICT_ACQUIT_MARGIN:
        case.verdict = Verdict.ACQUITTED
    elif margin >= VERDICT_LESSER_MARGIN:
        case.verdict = Verdict.LESSER
    else:
        case.verdict = Verdict.FULL

    case.status = CaseStatus.TRIED
    case.resolved_at = timezone.now()
    if case.verdict == Verdict.ACQUITTED:
        case.save(update_fields=["status", "verdict", "resolved_at"])
        _end_captivity(case)
        return case

    case.failed_outs += 1
    _apply_sentence(case)
    case.save(
        update_fields=[
            "status",
            "verdict",
            "resolved_at",
            "failed_outs",
            "sentence_kind",
            "sentence_amount",
        ]
    )
    _end_captivity(case)
    return case


def _argument_levels(participants: list[Persona]) -> list[int]:
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    check_type = CheckType.objects.filter(name=ADVOCACY_CHECK_TYPE_NAME).first()
    levels: list[int] = []
    for persona in participants:
        sheet = persona.character_sheet
        character = sheet.character if sheet is not None else None
        if check_type is None or character is None:
            levels.append(0)
            continue
        result = perform_check(character, check_type)
        levels.append(result.outcome.success_level if result.outcome else 0)
    return levels


def _apply_sentence(case: JusticeCase) -> None:
    """Sentence scales with prosecution weight; the lethal wall holds.

    Full-verdict catastrophic cases reach EXECUTION only when the accused is
    an NPC (no account) or a PC who opted in AND whose case is exhausted
    (>= EXECUTION_MIN_FAILED_OUTS spent outs). Everyone else caps at
    BRIG_TERM. Lesser verdicts fine or humiliate.
    """
    weight = case.prosecution_weight
    if case.verdict == Verdict.LESSER:
        if weight >= MAX_VALUE_FLOOR:
            case.sentence_kind = SentenceKind.BRIG_TERM
            case.sentence_amount = max(1, weight * BRIG_DAYS_PER_WEIGHT // 20)
        elif weight >= HUNTED_VALUE_FLOOR:
            case.sentence_kind = SentenceKind.HUMILIATION
            case.sentence_amount = 0
        else:
            case.sentence_kind = SentenceKind.FINE
            case.sentence_amount = weight * FINE_COPPERS_PER_WEIGHT
        _collect_fine(case)
        return

    # Full verdict.
    if weight >= MAX_VALUE_FLOOR and _execution_reachable(case):
        case.sentence_kind = SentenceKind.EXECUTION
        case.sentence_amount = 0
    elif weight >= HUNTED_VALUE_FLOOR:
        case.sentence_kind = SentenceKind.BRIG_TERM
        case.sentence_amount = max(1, weight * BRIG_DAYS_PER_WEIGHT // 10)
    else:
        case.sentence_kind = SentenceKind.FINE
        case.sentence_amount = weight * FINE_COPPERS_PER_WEIGHT * 2
    _collect_fine(case)


def _execution_reachable(case: JusticeCase) -> bool:
    """ADR-0023's wall: NPCs yes; PCs only with opt-in + an exhausted case."""
    account = _account_for(case.persona)
    if account is None:
        return True  # an NPC persona — execution is a legal terminal sentence
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        player_data = account.player_data
    except (AttributeError, ObjectDoesNotExist):
        player_data = None
    if player_data is None or not player_data.lethal_consequences_opt_in:
        return False
    return case.failed_outs >= EXECUTION_MIN_FAILED_OUTS


def _account_for(persona: Persona):
    sheet = persona.character_sheet
    if sheet is None:
        return None
    from world.magic.services.gain import account_for_sheet  # noqa: PLC0415

    return account_for_sheet(sheet)


def _collect_fine(case: JusticeCase) -> None:
    if case.sentence_kind != SentenceKind.FINE or case.sentence_amount <= 0:
        return
    from world.currency.services import get_or_create_purse  # noqa: PLC0415

    sheet = case.persona.character_sheet
    if sheet is None:
        return
    purse = get_or_create_purse(sheet)
    debit = min(purse.balance, case.sentence_amount)
    purse.balance -= debit
    purse.save(update_fields=["balance"])
