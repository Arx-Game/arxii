"""Answers at a pledge's close (#4333 slice 3, design 4).

An ``Answer`` is text staff wrote ahead for a being at one outcome tier. When a
closing rite resolves a pledge, :func:`deliver_pledge_answer` draws one and
sends it as a ``Vision`` through ``send_vision``:

* **The draw** (:func:`draw_answer`): the pledge type's active rows at the
  closing tier, then the being's rows with no pledge type at that tier, then the
  same two steps one tier lower, down to Critical Failure; nothing found means
  no vision (the closing award still lands). Each step is a weighted choice that
  leaves out answers this character has already drawn.
* **The body** (:func:`answer_body`): delay text; answer text followed by one
  sacrifice line per distinct facet recorded on the pledge's sacrifices, with
  any other sacrificed item listed by name; fact text; cost text; follow-up
  text. Parts the answer's tier may not carry (``answer_part_errors``) are left
  out even if a row holds them, so no fact is given below Success and no
  follow-up clue on Failure or Critical Failure.
* **Delivery** (:func:`deliver_answer`): the fact clue rides the vision's own
  clue slot; the follow-up clue is handed over by ``find_clue``, as a vision's
  clue is (#4331); the cost pool is applied at the answer's tier.
* **A short pool**: when the being's worship pool cannot pay for the vision the
  answer is held as a ``PendingAnswer`` and the daily tick
  (:func:`deliver_held_answers`) sends it once the pool can pay.

A lapsed pledge never reaches this module (Ruling 18).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.checks.outcome_utils import select_weighted
from world.worship.constants import (
    ANSWER_FACT_MIN_SUCCESS_LEVEL,
    ANSWER_FOLLOW_UP_MIN_SUCCESS_LEVEL,
    VISION_RESONANCE_POOL_COST,
)
from world.worship.exceptions import VisionError, VisionPoolInsufficient
from world.worship.models import Answer, PendingAnswer, Vision
from world.worship.types import AnswerDelivery

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.ceremonies.models import CeremonyOffering
    from world.character_sheets.models import CharacterSheet
    from world.clues.models import Clue
    from world.traits.models import CheckOutcome
    from world.worship.models import PledgeDetails

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Which parts a tier carries
# ---------------------------------------------------------------------------


def carries_fact(answer: Answer) -> bool:
    """Fact text and the fact clue: Success and Critical Success only."""
    return answer.outcome_tier.success_level >= ANSWER_FACT_MIN_SUCCESS_LEVEL


def carries_follow_up_clue(answer: Answer) -> bool:
    """The follow-up clue: Partial Success and above."""
    return answer.outcome_tier.success_level >= ANSWER_FOLLOW_UP_MIN_SUCCESS_LEVEL


def delivered_fact_clue(answer: Answer) -> Clue | None:
    """The fact clue this answer hands over, or None below Success."""
    return answer.fact_clue if carries_fact(answer) else None


def delivered_follow_up_clue(answer: Answer) -> Clue | None:
    """The follow-up clue this answer hands over, or None on Failure and below."""
    return answer.follow_up_clue if carries_follow_up_clue(answer) else None


# ---------------------------------------------------------------------------
# The draw
# ---------------------------------------------------------------------------


def _drawn_answer_ids(sheet: CharacterSheet) -> set[int]:
    """Answers this character has already drawn: delivered or held."""
    delivered = Vision.objects.filter(recipient=sheet, answer__isnull=False).values_list(
        "answer_id", flat=True
    )
    held = PendingAnswer.objects.filter(character_sheet=sheet).values_list("answer_id", flat=True)
    return set(delivered) | set(held)


def draw_answer(details: PledgeDetails, outcome_tier: CheckOutcome) -> Answer | None:
    """Choose the answer a closing rite of ``outcome_tier`` releases for ``details``.

    In order: (1) this pledge type's active rows at the tier; (2) the being's
    active rows with no pledge type at the tier; then (3) and (4) the same at the
    next lower tier, repeating down to the lowest; (5) None. Each step is a
    weighted choice among rows this character has not drawn before.
    """
    pledge = details.pledge
    rows = list(
        Answer.objects.filter(being_id=pledge.being_id, is_active=True)
        .filter(outcome_tier__success_level__lte=outcome_tier.success_level)
        .select_related("outcome_tier")
    )
    drawn = _drawn_answer_ids(details.character_sheet)
    rows = [row for row in rows if row.pk not in drawn and row.pledge_id in (None, pledge.pk)]
    for level in sorted({row.outcome_tier.success_level for row in rows}, reverse=True):
        at_level = [row for row in rows if row.outcome_tier.success_level == level]
        for scope in (pledge.pk, None):
            candidates = [row for row in at_level if row.pledge_id == scope]
            if candidates:
                return select_weighted(candidates)
    return None


# ---------------------------------------------------------------------------
# The body
# ---------------------------------------------------------------------------


def pledge_sacrifices(details: PledgeDetails) -> list[CeremonyOffering]:
    """The items sacrificed toward ``details``, oldest first."""
    from world.ceremonies.models import CeremonyOffering  # noqa: PLC0415

    return list(
        CeremonyOffering.objects.filter(pledge_details=details)
        .select_related("facet")
        .order_by("pk")
    )


def sacrifice_passage(answer: Answer, offerings: list[CeremonyOffering]) -> str:
    """The sacrifice lines for ``offerings``: each distinct recorded facet's line
    once; any other item (a repeated facet, a facet with no line, no facet at all)
    listed by name after the lines."""
    lines_by_facet = {line.facet_id: line.text.strip() for line in answer.sacrifice_lines.all()}
    used: set[int] = set()
    parts: list[str] = []
    others: list[str] = []
    for offering in offerings:
        facet_id = offering.facet_id
        if facet_id is not None and facet_id in lines_by_facet and facet_id not in used:
            used.add(facet_id)
            parts.append(lines_by_facet[facet_id])
        else:
            others.append(offering.item_name)
    if others:
        parts.append(f"Also sacrificed: {', '.join(others)}.")
    return " ".join(part for part in parts if part)


def answer_body(
    answer: Answer, offerings: list[CeremonyOffering], *, answer_text: str | None = None
) -> str:
    """The vision's prose: the parts this answer's tier carries, in reading order.

    ``answer_text`` replaces the answer's own main text: a GM whose level may adapt
    answers (#4333 slice 5) edits that one part before sending it live. The delay,
    fact, cost and follow-up text are never replaced.
    """
    main_text = answer.answer_text if answer_text is None else answer_text
    main = " ".join(
        part for part in (main_text.strip(), sacrifice_passage(answer, offerings)) if part
    )
    paragraphs = [answer.delay_text.strip(), main]
    if carries_fact(answer):
        paragraphs.append(answer.fact_text.strip())
    paragraphs.extend((answer.cost_text.strip(), answer.follow_up_text.strip()))
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def _apply_cost(sheet: CharacterSheet, answer: Answer) -> None:
    """Apply the cost pool's consequences at the answer's own tier."""
    if answer.cost_pool_id is None:
        return
    from world.checks.consequence_resolution import apply_pool_for_tier  # noqa: PLC0415
    from world.checks.types import ResolutionContext  # noqa: PLC0415

    apply_pool_for_tier(
        pool=answer.cost_pool,
        outcome_tier=answer.outcome_tier,
        context=ResolutionContext(character=sheet.character, outcome_tier=answer.outcome_tier),
    )


def _hand_over_follow_up(sheet: CharacterSheet, answer: Answer) -> None:
    clue = delivered_follow_up_clue(answer)
    roster_entry = sheet.roster_entry_or_none
    if clue is None or roster_entry is None:
        return
    from world.clues.services import find_clue  # noqa: PLC0415

    find_clue(roster_entry, clue)


def follow_up_footnote(clue: Clue) -> str:
    """How a vision names its follow-up clue: a mission by its kind, anything else as a clue."""
    from world.clues.constants import ClueTargetKind  # noqa: PLC0415

    noun = "A mission" if clue.target_kind == ClueTargetKind.MISSION else "A clue"
    return f"{noun} came with it: {clue.name}."


def answer_footnotes(answer: Answer) -> tuple[str, ...]:
    """The vision's footnotes for what the answer hands over (the demo's vision footer)."""
    notes: list[str] = []
    fact_clue = delivered_fact_clue(answer)
    if fact_clue is not None:
        notes.append(f"A clue came with it: {fact_clue.name}.")
    follow_up = delivered_follow_up_clue(answer)
    if follow_up is not None:
        notes.append(follow_up_footnote(follow_up))
    conditions = cost_condition_names(answer)
    if conditions:
        notes.append(f"Condition: {', '.join(conditions)}.")
    return tuple(notes)


def _hold(details: PledgeDetails, answer: Answer) -> AnswerDelivery:
    PendingAnswer.objects.get_or_create(
        pledge_details=details,
        defaults={"character_sheet": details.character_sheet, "answer": answer},
    )
    return AnswerDelivery(answer=answer, vision=None, held=True)


def deliver_answer(details: PledgeDetails, answer: Answer) -> AnswerDelivery:
    """Send ``answer`` to the pledge's character as a vision, or hold it.

    The vision spends the being's worship pool through ``send_vision``, carries
    the fact clue (Success and above), names the being unless the answer
    conceals its source, and records the answer and the pledge's prayer. The
    follow-up clue (Partial Success and above) and the cost follow. If the pool
    cannot pay, a ``PendingAnswer`` holds it for the daily tick.

    Not called inside an open transaction: ``send_vision`` pushes the vision to
    an online player as soon as its own record commits.
    """
    from world.worship.prayer_services import send_vision  # noqa: PLC0415

    sheet = details.character_sheet
    being = answer.being
    if being.resonance_pool < VISION_RESONANCE_POOL_COST:
        return _hold(details, answer)
    try:
        vision = send_vision(
            recipient=sheet,
            being=being,
            body=answer_body(answer, pledge_sacrifices(details)),
            sent_by=None,
            reveal_source=not answer.conceals_source,
            prayer=details.prayer,
            clue=delivered_fact_clue(answer),
            answer=answer,
            footnotes=answer_footnotes(answer),
        )
    except VisionPoolInsufficient:
        return _hold(details, answer)
    _hand_over_follow_up(sheet, answer)
    _apply_cost(sheet, answer)
    PendingAnswer.objects.filter(pledge_details=details).delete()
    return AnswerDelivery(answer=answer, vision=vision, held=False)


def deliver_live_answer(
    sheet: CharacterSheet, answer: Answer, *, sent_by: AccountDB, answer_text: str | None = None
) -> Vision:
    """Send ``answer`` to the character a GM answered live (#4333 slice 5, design 6).

    The same vision as a pledge's close sends, with no pledge behind it: no
    sacrifice passage, no prayer. The GM who chose it is the sender. The fact clue
    rides the vision, the follow-up clue and the cost follow, all from the answer
    as written. Raises ``VisionPoolInsufficient`` when the being's pool cannot pay
    now (a live answer is never held). Not called inside an open transaction.
    """
    from world.worship.prayer_services import send_vision  # noqa: PLC0415

    vision = send_vision(
        recipient=sheet,
        being=answer.being,
        body=answer_body(answer, [], answer_text=answer_text),
        sent_by=sent_by,
        reveal_source=not answer.conceals_source,
        prayer=None,
        clue=delivered_fact_clue(answer),
        answer=answer,
        footnotes=answer_footnotes(answer),
    )
    _hand_over_follow_up(sheet, answer)
    _apply_cost(sheet, answer)
    return vision


def deliver_pledge_answer(details: PledgeDetails, outcome_tier: CheckOutcome) -> AnswerDelivery:
    """Draw and deliver the answer a closing rite of ``outcome_tier`` releases.

    Returns an empty delivery when the being has no answer that fits the draw:
    no vision, and the closing award has already landed.
    """
    answer = draw_answer(details, outcome_tier)
    if answer is None:
        return AnswerDelivery(answer=None, vision=None, held=False)
    return deliver_answer(details, answer)


def deliver_held_answers() -> int:
    """The daily tick: send each held answer whose being's pool can now pay.

    Oldest first, so an earlier pledge is answered before a later one draws on
    the same pool. Returns how many were delivered. One failure is logged and
    the rest still run: a row whose vision refuses its attachments is logged
    and kept.
    """
    delivered = 0
    held = PendingAnswer.objects.select_related(
        "answer__being", "answer__outcome_tier", "pledge_details__character_sheet"
    ).order_by("created_at", "pk")
    for pending in held:
        if pending.answer.being.resonance_pool < VISION_RESONANCE_POOL_COST:
            continue
        try:
            outcome = deliver_answer(pending.pledge_details, pending.answer)
        except VisionError:  # an attachment no longer fits; the rest still run
            logger.exception("Held answer %s could not be delivered", pending.pk)
            continue
        if not outcome.held:
            delivered += 1
    return delivered


# ---------------------------------------------------------------------------
# What a delivered vision says came with it
# ---------------------------------------------------------------------------


def cost_condition_names(answer: Answer) -> list[str]:
    """The conditions the answer's cost pool applies at its tier, for the vision's
    footnote."""
    if answer.cost_pool_id is None:
        return []
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        resolve_pool_consequences,
    )
    from world.checks.constants import EffectType  # noqa: PLC0415

    names: list[str] = []
    for consequence in resolve_pool_consequences(answer.cost_pool):
        if consequence.outcome_tier_id != answer.outcome_tier_id:
            continue
        for effect in consequence.effects.select_related("condition_template"):
            template = effect.condition_template
            if effect.effect_type == EffectType.APPLY_CONDITION and template is not None:
                names.append(template.name)
    return names
