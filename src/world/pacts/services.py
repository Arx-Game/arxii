"""Being pacts (#4341): signing, crediting, grading each period, breach, renouncing.

* **Signing** (:func:`sign_being_pact`) marks her standing with the being as a PACT
  patronage (a Chosen's stays Chosen), applies the offer's condition at its first stage
  and opens one PACT_PERIOD project per FAVOR_EARNED commitment.
* **Serving**: ``bump_devotion`` calls :func:`record_pact_credit` for every positive
  favor write, which adds the favor to each open commitment period of her active pact
  with that being and itemises it as a ``PactCredit``. Deeds reach a pact's being
  through ``credit_pledge_deed``, under the shared weekly deed cap.
* **The period check**: PACT_PERIOD is TIERED_PERIOD, so the lifecycle tick resolves a
  period at its time limit. :func:`resolve_pact_period` picks the project's tier (met is
  Success, short is Failure) and ``resolve_project`` runs :func:`grade_pact_period`,
  which moves the condition, records the grading on ``PactPeriodDetails``, tells the
  holder alone and opens the next period. The project status machinery is the receipt:
  a period is graded once.

  - Met: severity eases by ``severity_per_miss * earned // required``, at most twice
    ``severity_per_miss``, never below the first stage's threshold. No roll.
  - Short: the rise is ``severity_per_miss * shortfall / required``, rounded up. When it
    would reach the next worse stage, that stage's resist check rolls first at its
    difficulty minus the favor band's ease (a botch lands as Failure): Critical Success
    adds nothing, Success stops one below the stage, Partial Success adds half (rounded
    up), Failure adds it all. A rise that stays inside the stage needs no roll. Only the
    next worse stage rolls: a failed roll applies the full rise even if it passes a
    second threshold (it cannot while ``severity_per_miss`` is no larger than the stage
    spacing, which the builder warns on).

* **Breach**: when the last stage applies the pact dissolves (BREACH), a PACT patronage
  is released, the stage's settle pool fires against the holder, she sees the closing
  text and the room the onlooker line, and an ease-out period opens. Every holder line
  and room line goes out when the transaction commits.
* **Renouncing** (:func:`renounce_pact`): RENOUNCED, the same release, the onlooker line,
  an ease-out period; the holder's text is returned for the action to deliver once.
* **Ease-out**: only the cost eases out. The first stage is the pact's benefit, so a
  pact that ends with its condition in the first stage removes the condition at once
  and opens no ease-out period. Otherwise a period with no commitment eases the
  condition by ``severity_per_miss``; when that would bring it into the first stage
  (or to zero) the condition is removed instead and nothing more opens.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import timedelta
import math
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from world.pacts.constants import CharacterPactCommitmentKind, CharacterPactEnding
from world.pacts.exceptions import NoActivePact, PactAlreadyHeld, PactOfferUnavailable
from world.pacts.models import CharacterPact, PactCredit, PactPeriodDetails
from world.pacts.types import (
    PactCard,
    PactCommitmentLine,
    PactOfferSummary,
    PactSourceLine,
    PactStageLine,
    PeriodGrade,
    RenouncedPact,
)
from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.worship.constants import DAYS_PER_GAME_WEEK, PledgeCreditSource

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.conditions.models import ConditionInstance, ConditionStage, ConditionTemplate
    from world.pacts.models import PactOffer, PactOfferCommitment
    from world.projects.models import Project
    from world.traits.models import CheckOutcome
    from world.worship.models import DevotionStanding, Pledge, WorshippedBeing
    from world.worship.types import FavorSource

#: Sources paid when a pledge resolves; they never count toward a pact period.
_RESOLUTION_SOURCES = frozenset({PledgeCreditSource.CLOSING, PledgeCreditSource.LAPSE})
#: Canonical project tiers: a met period (and an ease-out period) resolves at Success,
#: a short one at Failure (the seeded CheckOutcome rows ``resolve_project`` records).
_MET_OUTCOME_NAME = "Success"
_SHORT_OUTCOME_NAME = "Failure"
#: Resist tiers by success level: Critical Success, Success, Partial Success.
_CRITICAL_SUCCESS_LEVEL = 2
_SUCCESS_LEVEL = 1
_PARTIAL_SUCCESS_LEVEL = 0

MSG_ALREADY_HELD = "You already hold a pact with {being}."
MSG_NO_PACT = "You hold no pact with {being}."


# ---------------------------------------------------------------------------
# Reading pacts
# ---------------------------------------------------------------------------


def active_pact_with(sheet: CharacterSheet, being: WorshippedBeing) -> CharacterPact | None:
    """Her active pact with ``being``, or None."""
    return (
        CharacterPact.objects.filter(
            character_sheet=sheet,
            devotion_standing__being=being,
            dissolved_at__isnull=True,
        )
        .select_related("offer__being", "offer__condition", "devotion_standing")
        .first()
    )


def _staged_stages(condition: ConditionTemplate) -> list[ConditionStage]:
    """The condition's severity-threshold stages, best to worst."""
    return list(
        condition.stages.filter(severity_threshold__isnull=False)
        .select_related("resist_check_type", "settle_consequence_pool")
        .order_by("stage_order")
    )


def _effect_lines(condition: ConditionTemplate) -> tuple[list[str], dict[int, list[str]]]:
    """Each effect of ``condition`` as a line: (condition-wide lines, lines by stage pk).

    Modifier effects, granted capabilities and check modifiers, the effects a pact
    stage carries. Three queries, whatever the stage count.
    """
    from world.conditions.models import (  # noqa: PLC0415
        ConditionCapabilityEffect,
        ConditionCheckModifier,
        ConditionModifierEffect,
    )

    scope = Q(condition=condition) | Q(stage__condition=condition)
    rows: list[tuple[int | None, str]] = [
        (row.stage_id, f"{row.value:+d} {row.modifier_target.name}")
        for row in ConditionModifierEffect.objects.filter(scope).select_related("modifier_target")
    ]
    rows += [
        (row.stage_id, f"{row.capability.name} {row.value:+d}")
        for row in ConditionCapabilityEffect.objects.filter(scope).select_related("capability")
    ]
    rows += [
        (
            row.stage_id,
            f"{row.modifier_value:+d} to {(row.check_type or row.check_category).name} checks",
        )
        for row in ConditionCheckModifier.objects.filter(scope).select_related(
            "check_type", "check_category"
        )
    ]
    condition_wide = [line for stage_id, line in rows if stage_id is None]
    by_stage: dict[int, list[str]] = defaultdict(list)
    for stage_id, line in rows:
        if stage_id is not None:
            by_stage[stage_id].append(line)
    return condition_wide, by_stage


def _stage_lines(
    condition: ConditionTemplate,
) -> tuple[tuple[str, ...], tuple[PactStageLine, ...]]:
    condition_wide, by_stage = _effect_lines(condition)
    staged = _staged_stages(condition)
    stages = tuple(
        PactStageLine(
            name=stage.name,
            threshold=stage.severity_threshold,
            effects=tuple(by_stage.get(stage.pk, ())),
            is_last=index == len(staged) - 1,
        )
        for index, stage in enumerate(staged)
    )
    return tuple(condition_wide), stages


def _promises(offer: PactOffer) -> tuple[str, ...]:
    return tuple(
        row.notes
        for row in offer.commitments.all()
        if row.kind == CharacterPactCommitmentKind.CUSTOM and row.notes.strip()
    )


def pact_offer_summary(offer: PactOffer) -> PactOfferSummary:
    """The offer as the pledge card shows it: being, text, commitments, period, stages."""
    condition_effects, stages = _stage_lines(offer.condition)
    commitments = list(offer.commitments.all())
    return PactOfferSummary(
        being_name=offer.being.name,
        offer_name=offer.name,
        offer_text=offer.offer_text,
        period_weeks=offer.period_weeks,
        favor_per_period=tuple(
            row.amount
            for row in commitments
            if row.kind == CharacterPactCommitmentKind.FAVOR_EARNED
        ),
        promises=_promises(offer),
        condition_effects=condition_effects,
        stages=stages,
        commitments=tuple(
            PactCommitmentLine(kind=row.kind, amount=row.amount, notes=row.notes)
            for row in commitments
        ),
    )


def offered_pact_summary(pledge: Pledge) -> PactOfferSummary | None:
    """The pact ``pledge`` offers at its close, while that offer stands; else None."""
    offer = pledge.pact_offer
    if offer is None or not offer.is_active:
        return None
    return pact_offer_summary(offer)


def _open_periods(pact: CharacterPact) -> list[PactPeriodDetails]:
    return list(
        PactPeriodDetails.objects.filter(pact=pact, project__status=ProjectStatus.ACTIVE)
        .select_related("project", "commitment")
        .order_by("pk")
    )


def carded_pacts() -> QuerySet[CharacterPact]:
    """Every pact a card shows, newest first: active pacts, and ended pacts still easing
    out. Callers scope it (one sheet, or the sheets an account plays)."""
    return (
        CharacterPact.objects.filter(
            Q(dissolved_at__isnull=True)
            | Q(
                periods__commitment__isnull=True,
                periods__project__status=ProjectStatus.ACTIVE,
            )
        )
        .distinct()
        .select_related(
            "character_sheet",
            "offer__being",
            "offer__condition",
            "condition_instance__current_stage",
        )
        .order_by("-signed_at", "-pk")
    )


def _source_label(source: str, being_name: str) -> str:
    """How the card names one kind of favor source toward a pact period."""
    if source == PledgeCreditSource.DEED:
        return f"Deeds: resonances {being_name} favors, from missions and scenes"
    if source == PledgeCreditSource.RITE:
        return f"{being_name}'s rite, which you performed"
    return PledgeCreditSource(source).label


def pact_card(pact: CharacterPact) -> PactCard:
    """One pact as its holder's card shows it: the open period, its favor by source,
    the condition's stage and severity, and the offer's promises."""
    offer = pact.offer
    being_name = offer.being.name
    period = next(iter(_open_periods(pact)), None)
    sources: dict[str, int] = defaultdict(int)
    if period is not None:
        for credit in period.credits.order_by("pk"):
            sources[credit.source] += credit.credited
    condition_effects, stages = _stage_lines(offer.condition)
    instance = pact.condition_instance
    stage = instance.current_stage if instance is not None else None
    severity = instance.severity if instance is not None else 0
    next_threshold = next((line.threshold for line in stages if line.threshold > severity), None)
    project = period.project if period is not None else None
    return PactCard(
        pact=pact,
        being_name=being_name,
        offer_name=offer.name,
        period_weeks=offer.period_weeks,
        earned=project.current_progress if project is not None else 0,
        required=(project.threshold_target or 0) if project is not None else 0,
        time_limit=project.time_limit if project is not None else None,
        sources=tuple(
            PactSourceLine(label=_source_label(source, being_name), favor=favor)
            for source, favor in sources.items()
        ),
        stage_name=stage.name if stage is not None else "",
        severity=severity,
        next_stage_threshold=next_threshold,
        promises=_promises(offer),
        condition_effects=condition_effects,
        stages=stages,
        is_active=pact.is_active,
        dissolution_reason=pact.dissolution_reason,
    )


def pact_cards_for(sheet: CharacterSheet) -> list[PactCard]:
    """Her pact cards, newest first: active pacts, and ended pacts still easing out."""
    return [pact_card(pact) for pact in carded_pacts().filter(character_sheet=sheet)]


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def open_pact_period(
    pact: CharacterPact, commitment: PactOfferCommitment | None
) -> PactPeriodDetails:
    """Open one PACT_PERIOD project for ``commitment`` (None: an ease-out period).

    The period runs ``period_weeks`` game weeks from now; a commitment's favor amount is
    its threshold. The owner persona is the holder's current face, as a pledge's is.
    """
    from world.projects.models import Project  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    offer = pact.offer
    now = timezone.now()
    if commitment is None:
        description = f"Pact with {offer.being.name} easing out"
    else:
        description = f"Pact with {offer.being.name}: {commitment.amount} favor this period"
    project = Project.objects.create(
        kind=ProjectKind.PACT_PERIOD,
        completion_mode=CompletionMode.TIERED_PERIOD,
        status=ProjectStatus.ACTIVE,
        owner_persona=active_persona_for_sheet(pact.character_sheet),
        started_at=now,
        time_limit=now + timedelta(days=offer.period_weeks * DAYS_PER_GAME_WEEK),
        threshold_target=commitment.amount if commitment is not None else None,
        description=description,
    )
    return PactPeriodDetails.objects.create(project=project, pact=pact, commitment=commitment)


def _cancel_open_periods(pacts: list[CharacterPact], *, ease_out: bool) -> None:
    """Cancel the open commitment periods (or ease-out periods) of ``pacts``."""
    for details in PactPeriodDetails.objects.filter(
        pact__in=pacts,
        commitment__isnull=ease_out,
        project__status=ProjectStatus.ACTIVE,
    ).select_related("project"):
        project = details.project
        project.status = ProjectStatus.CANCELLED
        project.save(update_fields=["status", "updated_at"])


def _detach_instance(instance: ConditionInstance) -> None:
    """Clear every pact's link to ``instance`` before it is removed.

    The FK's SET_NULL runs as a queryset update, which the identity map never sees; a
    cached pact would keep pointing at the deleted row.
    """
    for pact in CharacterPact.objects.filter(condition_instance=instance):
        pact.condition_instance = None
        pact.save(update_fields=["condition_instance"])


def _fresh_condition_instance(sheet: CharacterSheet, offer: PactOffer) -> ConditionInstance:
    """The offer's condition on her at its first stage.

    A resolved instance left from an earlier pact is removed first so the apply starts
    fresh. An instance still easing out from an ended pact with the same condition is
    kept at its severity (the new pact does not wipe the old cost) and its ease-out
    chain is cancelled: the new pact's periods move it from here.
    """
    from world.conditions.services import (  # noqa: PLC0415
        apply_condition,
        get_condition_instance,
        remove_condition,
    )

    target = sheet.character
    condition = offer.condition
    existing = get_condition_instance(target, condition, include_suppressed=True)
    if existing is not None and existing.resolved_at is not None:
        _detach_instance(existing)
        remove_condition(target, condition, include_suppressed=True)
        existing = None
    if existing is not None:
        _cancel_open_periods(
            list(CharacterPact.objects.filter(character_sheet=sheet, condition_instance=existing)),
            ease_out=True,
        )
        return existing
    stages = _staged_stages(condition)
    severity = max(stages[0].severity_threshold, 1) if stages else 1
    result = apply_condition(
        target, condition, severity=severity, source_description=f"Pact: {offer.name}"
    )
    if result.instance is None:
        msg = f"The pact's condition could not be applied: {result.message}"
        raise PactOfferUnavailable(msg)
    return result.instance


def sign_being_pact(sheet: CharacterSheet, offer: PactOffer) -> CharacterPact:
    """Sign ``offer`` for ``sheet`` (spec section 7, step 3).

    Refused when the offer or its being is inactive, or she already holds an active pact
    with the being. Her standing becomes a PACT patronage when it was none (a released
    one is restored; a Chosen standing keeps its valence), the offer's condition goes on
    at its first stage, and one period opens per FAVOR_EARNED commitment.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.worship.models import DevotionStanding, PatronageValence  # noqa: PLC0415

    being = offer.being
    if not offer.is_active or not being.is_active:
        raise PactOfferUnavailable
    with transaction.atomic():
        CharacterSheet.objects.select_for_update().filter(pk=sheet.pk).exists()
        if active_pact_with(sheet, being) is not None:
            raise PactAlreadyHeld(MSG_ALREADY_HELD.format(being=being.name))
        standing, _ = DevotionStanding.objects.get_or_create(character_sheet=sheet, being=being)
        update_fields: list[str] = []
        if standing.valence is None:
            standing.valence = PatronageValence.PACT
            standing.established_at = timezone.now()
            update_fields += ["valence", "established_at"]
        if standing.released_at is not None:
            standing.released_at = None
            update_fields.append("released_at")
        if update_fields:
            standing.save(update_fields=update_fields)
        instance = _fresh_condition_instance(sheet, offer)
        pact = CharacterPact.objects.create(
            character_sheet=sheet,
            offer=offer,
            devotion_standing=standing,
            condition_instance=instance,
        )
        for commitment in offer.commitments.filter(
            kind=CharacterPactCommitmentKind.FAVOR_EARNED
        ).order_by("pk"):
            open_pact_period(pact, commitment)
    return pact


# ---------------------------------------------------------------------------
# Serving: favor credited to the open periods
# ---------------------------------------------------------------------------


def record_pact_credit(
    sheet: CharacterSheet,
    being: WorshippedBeing,
    credited: int,
    source: FavorSource | None,
    *,
    base: int = 0,
) -> list[PactCredit]:
    """Credit ``credited`` favor to every open commitment period of her pact with ``being``.

    Called by ``bump_devotion`` beside ``record_pledge_credit``. A pledge's closing and
    lapse awards are not served favor and never count. ``base`` is the favor before the
    earning rate that this write takes from the weekly deed cap; the caller passes 0 when
    the write's ``PledgeCredit`` already counts it. It is stored on the first period's
    row only, so a pact with several open periods counts one write once.
    """
    if credited <= 0:
        return []
    kind = source.kind if source is not None else PledgeCreditSource.OTHER
    if kind in _RESOLUTION_SOURCES:
        return []
    periods = list(
        PactPeriodDetails.objects.filter(
            pact__character_sheet=sheet,
            pact__devotion_standing__being=being,
            pact__dissolved_at__isnull=True,
            commitment__isnull=False,
            project__status=ProjectStatus.ACTIVE,
        ).select_related("project")
    )
    if not periods:
        return []
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    week = get_current_game_week()
    written: list[PactCredit] = []
    for index, period in enumerate(periods):
        project = period.project
        project.current_progress += credited
        project.save(update_fields=["current_progress", "updated_at"])
        written.append(
            PactCredit.objects.create(
                period=period,
                source=kind,
                base=max(base, 0) if index == 0 else 0,
                credited=credited,
                game_week=week,
            )
        )
    return written


def pact_beings_for(sheet: CharacterSheet) -> list[WorshippedBeing]:
    """The beings whose active pact with her has an open commitment period, oldest first.

    A pact with no FAVOR_EARNED commitment has no period to credit, so a deed favor
    write for its being would land in no ``PactCredit`` and escape the weekly deed cap;
    such a pact earns no deed favor.
    """
    return [
        pact.offer.being
        for pact in CharacterPact.objects.filter(
            character_sheet=sheet,
            dissolved_at__isnull=True,
            periods__commitment__isnull=False,
            periods__project__status=ProjectStatus.ACTIVE,
        )
        .distinct()
        .select_related("offer__being")
        .order_by("signed_at", "pk")
    ]


def pact_deed_favor_this_week(sheet: CharacterSheet) -> int:
    """Base deed favor her pact credits took from this week's deed cap.

    Exact and counted once: ``PactCredit.base`` is 0 on every row whose favor write is
    already counted (on its ``PledgeCredit``, or on the first period's row), so the sum
    beside the pledge credits' base is the week's whole deed favor.
    """
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    total = PactCredit.objects.filter(
        period__pact__character_sheet=sheet,
        source=PledgeCreditSource.DEED,
        game_week=get_current_game_week(),
    ).aggregate(total=Sum("base"))["total"]
    return total or 0


# ---------------------------------------------------------------------------
# The period check
# ---------------------------------------------------------------------------


def resolve_pact_period(project: Project) -> None:
    """The PACT_PERIOD tiered resolver: Success when met (or easing out), else Failure.

    ``grade_pact_period`` does the grading. A short period rolls only the next worse
    stage's resist check, even when the rise would pass a second threshold.
    """
    from world.projects.services import resolve_project  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    details = project.pact_period_details
    met = details.commitment_id is None or project.current_progress >= (
        project.threshold_target or 0
    )
    outcome = CheckOutcome.objects.get(name=_MET_OUTCOME_NAME if met else _SHORT_OUTCOME_NAME)
    resolve_project(project, outcome_tier=outcome)


def grade_pact_period(project: Project, outcome_tier: CheckOutcome | None) -> None:  # noqa: ARG001
    """The PACT_PERIOD kind handler, run once by ``resolve_project``.

    Grades from the project itself (the tier only mirrors met/short): a commitment
    period of an active pact moves the condition and may breach; any other period
    eases it out.
    """
    details = project.pact_period_details
    pact = details.pact
    if details.commitment_id is None:
        _grade_ease_out_period(details)
    elif pact.is_active:
        _grade_commitment_period(details)
    else:
        # A commitment period left open on an ended pact (ending cancels them): nothing
        # is owed any more, and the pact's own ease-out chain moves the condition.
        _record(details, pact.condition_instance, change=0, resist=None)


def _tell(sheet: CharacterSheet, lines: list[str]) -> None:
    """One system message to the holder alone, kept for her if she is offline.

    Sent when the surrounding transaction commits: grading runs inside the project
    tick's atomic block, and a later raise there rolls the grading back, so a line sent
    at once would report a roll the next tick makes again.
    """
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    body = "\n".join(line for line in lines if line)
    if body:
        transaction.on_commit(
            lambda: send_narrative_message(
                recipients=[sheet], body=body, category=NarrativeCategory.SYSTEM
            )
        )


def _tell_room(pact: CharacterPact) -> None:
    """The offer's onlooker line to the holder's room when the pact ends, if written.

    Sent on commit, as the holder's lines are. The authored line is all the room
    hears; it never names a secret being itself.
    """
    from world.scenes.narrator import narrate_room_outcome  # noqa: PLC0415

    line = pact.offer.onlooker_line.strip()
    room = pact.character_sheet.character.location
    if line and room is not None:
        transaction.on_commit(lambda: narrate_room_outcome(room, line))


def _next_worse_stage(
    stages: list[ConditionStage], current: ConditionStage | None
) -> ConditionStage | None:
    if current is None:
        return stages[0] if stages else None
    return next((stage for stage in stages if stage.stage_order > current.stage_order), None)


def _record(
    details: PactPeriodDetails,
    instance: ConditionInstance | None,
    *,
    change: int,
    resist: CheckOutcome | None,
) -> None:
    details.severity_change = change
    details.resist_outcome = resist
    details.stage_after = instance.current_stage if instance is not None else None
    details.save(update_fields=["severity_change", "resist_outcome", "stage_after"])


def _ease_met(
    details: PactPeriodDetails,
    instance: ConditionInstance,
    stages: list[ConditionStage],
    earned: int,
    required: int,
) -> int:
    """A met period eases severity, capped at twice per-miss, floored at the first stage."""
    from world.conditions.services import decay_condition_severity  # noqa: PLC0415

    per_miss = details.pact.offer.severity_per_miss
    ease = min(per_miss * earned // max(required, 1), 2 * per_miss)
    floor = max(stages[0].severity_threshold, 1) if stages else 1
    ease = max(min(ease, instance.severity - floor), 0)
    if ease:
        decay_condition_severity(instance, ease)
    return ease


def _resist_rise(
    sheet: CharacterSheet,
    being: WorshippedBeing,
    instance: ConditionInstance,
    worse: ConditionStage,
    rise: int,
) -> tuple[int, CheckResult, list[str]]:
    """Roll ``worse``'s resist check and return (rise to apply, result, message lines)."""
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.worship.invocation_services import favor_ease_for  # noqa: PLC0415
    from world.worship.sacrifice_services import lift_botch  # noqa: PLC0415

    ease = favor_ease_for(sheet, being)
    ease_points = ease.points if ease is not None else 0
    difficulty = max(worse.resist_difficulty - ease_points, 0)
    raw = perform_check_with_modifiers(
        sheet.character, worse.resist_check_type, target_difficulty=difficulty
    )
    result = replace(raw, outcome=lift_botch(raw.outcome))
    level = result.success_level
    severity = instance.severity
    threshold = worse.severity_threshold
    if level >= _CRITICAL_SUCCESS_LEVEL:
        applied, verdict = 0, "nothing is added"
    elif level >= _SUCCESS_LEVEL:
        applied = max(threshold - 1 - severity, 0)
        verdict = f"severity stops at {severity + applied}, one below {worse.name}"
    elif level == _PARTIAL_SUCCESS_LEVEL:
        applied = math.ceil(rise / 2)
        verdict = f"half the rise applies ({applied})"
    else:
        applied, verdict = rise, "the full rise applies"
    eased = (
        f" minus {ease_points}, because your favor with {being.name} eases it"
        if ease_points
        else ""
    )
    outcome_name = result.outcome.name if result.outcome is not None else "no result"
    lines = [
        f"That would raise severity by {rise} (to {severity + rise}) and reach {worse.name}. "
        f"Resist check: {worse.resist_difficulty}{eased}. Result: {outcome_name}, so {verdict}."
    ]
    return applied, result, lines


def _eased_line(
    instance: ConditionInstance, eased: int, stage_before: ConditionStage | None
) -> str:
    """What a met period did: the ease, and the stage it went back to, if it changed."""
    line = f"Severity eases by {eased} (to {instance.severity})." if eased else "Severity holds."
    if instance.current_stage != stage_before and instance.current_stage is not None:
        line += f" {instance.current_stage.name} now applies."
    return line


def _grade_commitment_period(details: PactPeriodDetails) -> PeriodGrade:
    from world.conditions.services import advance_condition_severity  # noqa: PLC0415

    pact = details.pact
    offer = pact.offer
    being = offer.being
    sheet = pact.character_sheet
    project = details.project
    earned = project.current_progress
    required = project.threshold_target or 0
    instance = pact.condition_instance
    stages = _staged_stages(offer.condition)
    stage_before = instance.current_stage if instance is not None else None
    resist: CheckResult | None = None
    lines: list[str]
    change = 0
    if earned >= required:
        lines = [f"Your pact with {being.name}: {earned} of {required} favor this period."]
        if instance is not None:
            change = -_ease_met(details, instance, stages, earned, required)
            lines.append(_eased_line(instance, -change, stage_before))
    else:
        short = required - earned
        lines = [
            f"Your pact with {being.name}: {earned} of {required} favor this period, {short} short."
        ]
        if instance is not None:
            rise = math.ceil(offer.severity_per_miss * short / required)
            worse = _next_worse_stage(stages, instance.current_stage)
            reaches = worse is not None and instance.severity + rise >= worse.severity_threshold
            if reaches and worse.resist_check_type_id is not None:
                rise, resist, resist_lines = _resist_rise(sheet, being, instance, worse, rise)
                lines += resist_lines
            # A worse stage with no resist check authored takes the full rise unrolled.
            if rise > 0:
                advance_condition_severity(instance, rise)
            change = rise
            if instance.current_stage != stage_before and instance.current_stage is not None:
                now_applies = f"{instance.current_stage.name} now applies."
                if stages and instance.current_stage_id != stages[-1].pk:
                    now_applies += (
                        f" Earn {required} next period to ease it by {offer.severity_per_miss}."
                    )
                lines.append(now_applies)
            elif not reaches:
                lines.append(f"Severity rises by {rise} (to {instance.severity}). No stage change.")
    _record(details, instance, change=change, resist=resist.outcome if resist else None)
    last = stages[-1] if stages else None
    breached = (
        instance is not None
        and last is not None
        and instance.current_stage_id == last.pk
        and stage_before != last
    )
    _tell(sheet, lines)
    if breached:
        _breach(pact, details, resist)
    else:
        open_pact_period(pact, details.commitment)
    return PeriodGrade(
        earned=earned,
        required=required,
        severity_change=change,
        resist_outcome=resist.outcome.name if resist and resist.outcome else "",
        stage_before=stage_before.name if stage_before is not None else "",
        stage_after=(
            instance.current_stage.name
            if instance is not None and instance.current_stage is not None
            else ""
        ),
        breached=breached,
    )


def _release_if_pact(standing: DevotionStanding | None) -> bool:
    """Release a PACT patronage (D5); a Chosen's own patronage is kept. True if released."""
    from world.worship.models import PatronageValence  # noqa: PLC0415
    from world.worship.services import release_patronage  # noqa: PLC0415

    if standing is None or standing.valence != PatronageValence.PACT:
        return False
    release_patronage(standing)
    return True


def _end_pact(pact: CharacterPact, reason: str, *, keep: PactPeriodDetails | None = None) -> bool:
    """Dissolve ``pact``, cancel its other open commitment periods, release (D5)."""
    pact.dissolved_at = timezone.now()
    pact.dissolution_reason = reason
    pact.save(update_fields=["dissolved_at", "dissolution_reason"])
    for details in PactPeriodDetails.objects.filter(
        pact=pact, commitment__isnull=False, project__status=ProjectStatus.ACTIVE
    ).select_related("project"):
        if keep is not None and details.pk == keep.pk:
            continue
        project = details.project
        project.status = ProjectStatus.CANCELLED
        project.save(update_fields=["status", "updated_at"])
    return _release_if_pact(pact.devotion_standing)


def _in_benefit_range(severity: int, stages: list[ConditionStage]) -> bool:
    """True when ``severity`` sits in the first stage (the pact's benefit) or below it."""
    if len(stages) <= 1:  # a lone stage is only the benefit
        return True
    return severity < stages[1].severity_threshold


def _remove_pact_condition(pact: CharacterPact) -> str:
    """Remove the pact's condition from her; return the condition's name."""
    from world.conditions.services import remove_condition  # noqa: PLC0415

    instance = pact.condition_instance
    name = instance.condition.name
    _detach_instance(instance)
    remove_condition(pact.character_sheet.character, instance.condition, include_suppressed=True)
    pact.condition_instance = None
    return name


def _drop_benefit(pact: CharacterPact) -> str:
    """At the end, a condition still in its first stage (the benefit) goes at once.

    Returns the removed condition's name, or "" when the cost is left to ease out.
    """
    instance = pact.condition_instance
    if instance is None:
        return ""
    if not _in_benefit_range(instance.severity, _staged_stages(pact.offer.condition)):
        return ""
    return _remove_pact_condition(pact)


def _ended_lines(pact: CharacterPact, *, released: bool, gone: str = "") -> list[str]:
    being = pact.offer.being
    first = (
        f"{being.name} is no longer your patron."
        if released
        else f"Your pact with {being.name} has ended."
    )
    lines = [f"{first} Codex entries and clues you gained are kept."]
    if gone:
        lines.append(f"{gone} is gone.")
        return lines
    instance = pact.condition_instance
    if instance is not None and instance.current_stage is not None:
        lines.append(
            f"{instance.current_stage.name} eases by {pact.offer.severity_per_miss} each "
            "period until it is gone."
        )
    return lines


def _open_ease_out(pact: CharacterPact) -> PactPeriodDetails | None:
    """Open the pact's ease-out period, unless its condition is gone or one is open."""
    if pact.condition_instance is None:
        return None
    if PactPeriodDetails.objects.filter(
        pact=pact, commitment__isnull=True, project__status=ProjectStatus.ACTIVE
    ).exists():
        return None
    return open_pact_period(pact, None)


def _fire_settle_pool(pact: CharacterPact, check_result: CheckResult | None) -> None:
    """The breached stage's settle pool, against the holder only, if one is authored.

    The pool's tier comes from the failed resist roll. A breach reached with no roll (a
    last stage with no resist check authored) has no result to pick a tier from, so no
    pool fires.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        select_consequence_from_result,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.npc_services.allegiance_outcomes import settle_pool_for  # noqa: PLC0415

    instance = pact.condition_instance
    if instance is None or check_result is None:
        return
    pool = settle_pool_for(instance)
    if pool is None:
        return
    holder = pact.character_sheet.character
    pending = select_consequence_from_result(holder, check_result, pool.cached_consequences)
    apply_resolution(pending, ResolutionContext(character=holder, target=holder))


def _breach(
    pact: CharacterPact, details: PactPeriodDetails, check_result: CheckResult | None
) -> None:
    released = _end_pact(pact, CharacterPactEnding.BREACH, keep=details)
    _fire_settle_pool(pact, check_result)
    gone = _drop_benefit(pact)
    _tell(
        pact.character_sheet,
        [pact.offer.closing_text.strip(), *_ended_lines(pact, released=released, gone=gone)],
    )
    _tell_room(pact)
    _open_ease_out(pact)


def _grade_ease_out_period(details: PactPeriodDetails) -> None:
    """Ease the ended pact's cost by per-miss. Easing into the first stage (the pact's
    benefit) or to zero removes the condition instead; otherwise the next period opens."""
    from world.conditions.services import decay_condition_severity  # noqa: PLC0415

    pact = details.pact
    instance = pact.condition_instance
    if instance is None:
        _record(details, None, change=0, resist=None)
        return
    stage_before = instance.current_stage
    stage_name = stage_before.name if stage_before is not None else instance.condition.name
    amount = min(pact.offer.severity_per_miss, instance.severity)
    after = instance.severity - amount
    if after <= 0 or _in_benefit_range(after, _staged_stages(pact.offer.condition)):
        _record(details, None, change=-instance.severity, resist=None)
        gone = _remove_pact_condition(pact)
        _tell(pact.character_sheet, [f"{gone} is gone."])
        return
    decay_condition_severity(instance, amount)
    _record(details, instance, change=-amount, resist=None)
    line = f"{stage_name} eases by {amount}."
    if instance.current_stage != stage_before and instance.current_stage is not None:
        line += f" {instance.current_stage.name} now applies."
    _tell(pact.character_sheet, [line])
    open_pact_period(pact, None)


# ---------------------------------------------------------------------------
# Renouncing
# ---------------------------------------------------------------------------


def renounce_pact(sheet: CharacterSheet, being: WorshippedBeing) -> RenouncedPact:
    """End her active pact with ``being`` (RENOUNCED): release (D5) and ease out.

    The room hears the offer's onlooker line on commit. What she is told is returned
    for the caller to deliver once (the action's own message), not sent here.
    """
    with transaction.atomic():
        pact = active_pact_with(sheet, being)
        if pact is None:
            raise NoActivePact(MSG_NO_PACT.format(being=being.name))
        released = _end_pact(pact, CharacterPactEnding.RENOUNCED)
        gone = _drop_benefit(pact)
        _open_ease_out(pact)
        _tell_room(pact)
    message = " ".join(
        [
            f"You renounce your pact with {being.name}.",
            *_ended_lines(pact, released=released, gone=gone),
        ]
    )
    return RenouncedPact(pact=pact, message=message)
