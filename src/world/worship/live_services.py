"""A GM answers a rite live (#4333 slice 5, design 6; walkthrough D; completes #3298).

A tier 1 or 2 rite performed in a scene a GM runs asks that GM, through a
scene-bound ``BEING_ANSWER`` prompt, whether the being answers. The GM's panel
(:func:`live_panel`) lists the being's authored answers at or below the rolled
tier (its general answers: a pledge type's answers belong to a pledge) and its
miracles. The GM sends one answer, or one eligible miracle, or sends nothing.

* **The limit** (:func:`live_limit_reason`): a being answers a given character
  live at most once per game week, answers and miracles counted together, per
  being and character. A confirmed live prompt is the record of each, so the two
  share one count. A being already at the limit is not prompted for.
* **Never a closing rite**: only ``PerformWorshipRiteAction`` calls
  :func:`route_live_answer`; a pledge's closing rite goes through
  ``ClosePledgeAction`` and its answer is the pledge route's.
* **Adapting** (:func:`send_live_answer` with ``text``): only a GM whose level has
  ``GMLevelCap.may_adapt_answers`` edits an answer's main text. Nobody edits its
  clue, cost or follow-up.
* **Miracles** are checked by the helper ``fire_divine_intervention`` also uses
  (``services.miracle_ineligibility``) and performed through
  ``perform_divine_intervention``.
* **Dismissing sends nothing** (``steward_services.dismiss_being_answer`` closes a
  prompt with no pledge without drawing).

A prompt (and every sibling copy sent to another GM of the same scene) is
resolved under row locks before anything is sent, so two GMs cannot both answer.
The vision itself goes out after that commits, since ``send_vision`` pushes it to
an online player as its own record commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Count

from world.worship.constants import STEWARD_ANSWER_TEXT_MAX_LENGTH, VISION_RESONANCE_POOL_COST
from world.worship.exceptions import StewardAnswerError, VisionPoolInsufficient
from world.worship.models import Answer, Miracle, WorshipRitePerformance
from world.worship.types import LiveAnswerOption, LiveMiracleOption, LivePanel, LiveSend

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.gm.models import GMPrompt
    from world.scenes.models import Scene

MSG_NOT_PENDING = "That prompt has already been answered."
MSG_NOT_LIVE = "That prompt is not a rite waiting for a live answer."
MSG_ONE_CHOICE = "Choose one answer or one miracle."
MSG_NOT_AN_OPTION = "That answer is not one this being can send at this roll."
MSG_NOT_A_MIRACLE = "That miracle is not one of this being's."
MSG_LIMIT = "{being} has already answered {name} live this game week."
MSG_ADAPT_NOT_ALLOWED = "Your GM level does not allow editing an answer."
MSG_TEXT_LONG = f"An answer is at most {STEWARD_ANSWER_TEXT_MAX_LENGTH} characters."
MSG_POOL_SHORT = (
    "{being}'s worship pool cannot pay for a vision now. Choose a miracle, or dismiss the prompt."
)
MSG_ANSWER_LOST = "{being} could not send the vision just now; the prompt is open again."
MSG_MIRACLE_LOST = "That miracle could not be performed just now."
NOTE_ANSWERED_ELSEWHERE = "Another GM of the scene answered."
NOTE_ANSWER = "Sent an authored answer."
NOTE_ADAPTED = "Sent an authored answer with edited text."
NOTE_MIRACLE = "Performed a miracle."
NOTE_SCENE_ENDED = "The scene ended before an answer."


# ---------------------------------------------------------------------------
# The limit
# ---------------------------------------------------------------------------


def _current_week():
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    return get_current_game_week()


def live_answers_this_week(being, sheet) -> int:
    """How many times ``being`` has answered ``sheet`` live in the current game
    week, answers and miracles together: the confirmed live prompts of rites
    performed this week."""
    from world.gm.constants import GMPromptKind, GMPromptStatus  # noqa: PLC0415
    from world.gm.models import GMPrompt as GMPromptModel  # noqa: PLC0415

    return GMPromptModel.objects.filter(
        kind=GMPromptKind.BEING_ANSWER,
        status=GMPromptStatus.CONFIRMED,
        character_sheet=sheet,
        rite_performance__rite__being=being,
        rite_performance__game_week=_current_week(),
    ).count()


def live_limit_reason(being, sheet) -> str:
    """Why ``being`` may not answer ``sheet`` live now, or "" when it may."""
    if live_answers_this_week(being, sheet) == 0:
        return ""
    return MSG_LIMIT.format(being=being.name, name=sheet.character.db_key)


# ---------------------------------------------------------------------------
# What the panel offers
# ---------------------------------------------------------------------------


def live_answer_options(being, tier) -> list[Answer]:
    """The being's active general answers at or below ``tier``, highest tier first."""
    return list(
        Answer.objects.filter(
            being=being,
            pledge__isnull=True,
            is_active=True,
            outcome_tier__success_level__lte=tier.success_level,
        )
        .select_related("outcome_tier")
        .order_by("-outcome_tier__success_level", "pk")
    )


def live_miracle_options(being) -> list[Miracle]:
    """The being's active miracles, in the order the divine intervention check
    tries them."""
    return list(
        Miracle.objects.filter(being=being, is_active=True)
        .select_related("being")
        .order_by("sort_order", "pk")
    )


def may_adapt_answers(account: AccountDB | None) -> bool:
    """Whether ``account``'s GM level may edit an answer before sending it live."""
    from world.gm.models import GMProfile  # noqa: PLC0415
    from world.gm.services import cap_for_profile  # noqa: PLC0415

    if account is None:
        return False
    profile = GMProfile.objects.filter(account=account).first()
    if profile is None:
        return False
    cap = cap_for_profile(profile)
    return cap is not None and cap.may_adapt_answers


def _live_prompt_performance(prompt: GMPrompt) -> WorshipRitePerformance:
    from world.gm.constants import GMPromptKind  # noqa: PLC0415

    if prompt.kind != GMPromptKind.BEING_ANSWER or prompt.rite_performance_id is None:
        raise StewardAnswerError(MSG_NOT_LIVE)
    return prompt.rite_performance


def is_live_prompt(prompt: GMPrompt) -> bool:
    """Whether ``prompt`` is a rite waiting for a live answer, not a stewarded close."""
    return prompt.rite_performance_id is not None


def live_panel(prompt: GMPrompt, *, account: AccountDB | None) -> LivePanel:
    """The answer panel for a live prompt, as ``account`` (the viewing GM) sees it."""
    from world.worship.services import miracle_ineligibility  # noqa: PLC0415

    performance = _live_prompt_performance(prompt)
    rite = performance.rite
    being = rite.being
    sheet = performance.character_sheet
    tier = performance.outcome_tier
    used = dict(
        Answer.objects.filter(being=being).annotate(sent=Count("visions")).values_list("pk", "sent")
    )
    return LivePanel(
        being=being,
        sheet=sheet,
        rite=rite,
        tier=tier,
        answers=[
            LiveAnswerOption(answer=row, used_count=used.get(row.pk, 0))
            for row in live_answer_options(being, tier)
        ],
        miracles=[
            LiveMiracleOption(miracle=row, reason=miracle_ineligibility(sheet, row))
            for row in live_miracle_options(being)
        ],
        may_adapt=may_adapt_answers(account),
        limit_reason=live_limit_reason(being, sheet),
    )


# ---------------------------------------------------------------------------
# Raising the prompt
# ---------------------------------------------------------------------------


def route_live_answer(performance: WorshipRitePerformance, scene: Scene) -> list[GMPrompt]:
    """Prompt the scene's GMs to answer a rite just performed in ``scene``.

    Returns the prompts created (one per GM who did not mute the Being answers
    group, never the performer's own player); empty when the being already
    answered this character live this week, when it has no answer at the roll and
    no miracle to offer, or when no GM wants it. The rite's award has already
    landed: the prompt adds an answer, it never gates the award.
    """
    from world.gm.constants import GMPromptKind  # noqa: PLC0415
    from world.gm.prompt_services import route_narratable_event  # noqa: PLC0415
    from world.gm.types import NarratableEvent  # noqa: PLC0415

    being = performance.rite.being
    sheet = performance.character_sheet
    if live_limit_reason(being, sheet):
        return []
    if not live_answer_options(being, performance.outcome_tier) and not live_miracle_options(being):
        return []
    return route_narratable_event(
        NarratableEvent(
            kind=GMPromptKind.BEING_ANSWER,
            scene=scene,
            character_sheet=sheet,
            rite_performance=performance,
        )
    )


# ---------------------------------------------------------------------------
# Resolving the prompt
# ---------------------------------------------------------------------------


def _lock_and_resolve(prompt: GMPrompt, *, resolver: AccountDB | None, note: str) -> None:
    """Confirm ``prompt`` and close its sibling copies, or refuse.

    Every copy of the event (``event_group``) is locked first, so two GMs of one
    scene answering together are serialised: the second finds the first's copy
    confirmed. The limit is asked under the same lock. A copy that is not PENDING
    is read from the database, never the identity map.
    """
    from world.gm.constants import GMPromptStatus  # noqa: PLC0415
    from world.gm.models import GMPrompt as GMPromptModel  # noqa: PLC0415

    with transaction.atomic():
        statuses = dict(
            GMPromptModel.objects.select_for_update()
            .filter(event_group=prompt.event_group)
            .order_by("pk")
            .values_list("pk", "status")
        )
        current = statuses.get(prompt.pk)
        if current != GMPromptStatus.PENDING:
            prompt.status = current or prompt.status
            raise StewardAnswerError(MSG_NOT_PENDING)
        performance = _live_prompt_performance(prompt)
        reason = live_limit_reason(performance.rite.being, performance.character_sheet)
        if reason:
            raise StewardAnswerError(reason)
        siblings = [
            pk
            for pk, status in statuses.items()
            if pk != prompt.pk and status == GMPromptStatus.PENDING
        ]
        for sibling in GMPromptModel.objects.filter(pk__in=siblings):
            sibling.status = GMPromptStatus.DISMISSED
            sibling.resolution_note = NOTE_ANSWERED_ELSEWHERE
            sibling.save(update_fields=["status", "resolution_note"])
        prompt.status = GMPromptStatus.CONFIRMED
        prompt.resolved_by = resolver
        prompt.resolution_note = note
        prompt.save(update_fields=["status", "resolved_by", "resolution_note"])


def _reopen(prompt: GMPrompt) -> None:
    """Put a prompt whose send failed back to PENDING, so the GM may choose again."""
    from world.gm.constants import GMPromptStatus  # noqa: PLC0415

    prompt.status = GMPromptStatus.PENDING
    prompt.resolved_by = None
    prompt.resolution_note = ""
    prompt.save(update_fields=["status", "resolved_by", "resolution_note"])


def send_live_answer(
    prompt: GMPrompt,
    *,
    resolver: AccountDB,
    answer: Answer | None = None,
    miracle: Miracle | None = None,
    text: str = "",
) -> LiveSend:
    """The GM answers the rite: one authored answer (with its main text edited only
    when ``resolver``'s level allows), or one eligible miracle.

    Authorization (the addressed GM, or staff) is the caller's. The weekly limit,
    the answer's tier, the miracle's eligibility and the pool are all checked here.
    """
    from world.worship.answer_services import deliver_live_answer  # noqa: PLC0415

    performance = _live_prompt_performance(prompt)
    being = performance.rite.being
    sheet = performance.character_sheet
    if (answer is None) == (miracle is None):
        raise StewardAnswerError(MSG_ONE_CHOICE)
    if miracle is not None:
        if text.strip():
            raise StewardAnswerError(MSG_ONE_CHOICE)
        return _send_miracle(prompt, resolver=resolver, performance=performance, miracle=miracle)
    words = text.strip()
    if answer.pk not in {row.pk for row in live_answer_options(being, performance.outcome_tier)}:
        raise StewardAnswerError(MSG_NOT_AN_OPTION)
    if words:
        if not may_adapt_answers(resolver):
            raise StewardAnswerError(MSG_ADAPT_NOT_ALLOWED)
        if len(words) > STEWARD_ANSWER_TEXT_MAX_LENGTH:
            raise StewardAnswerError(MSG_TEXT_LONG)
    if being.resonance_pool < VISION_RESONANCE_POOL_COST:
        raise StewardAnswerError(MSG_POOL_SHORT.format(being=being.name))
    _lock_and_resolve(prompt, resolver=resolver, note=NOTE_ADAPTED if words else NOTE_ANSWER)
    try:
        vision = deliver_live_answer(
            sheet, answer, sent_by=resolver, answer_text=words if words else None
        )
    except VisionPoolInsufficient as exc:
        # The pool was spent between the check and the send.
        _reopen(prompt)
        raise StewardAnswerError(MSG_ANSWER_LOST.format(being=being.name)) from exc
    return LiveSend(being=being, sheet=sheet, answer=answer, vision=vision)


def _send_miracle(
    prompt: GMPrompt,
    *,
    resolver: AccountDB,
    performance: WorshipRitePerformance,
    miracle: Miracle,
) -> LiveSend:
    from world.worship.services import (  # noqa: PLC0415
        miracle_ineligibility,
        perform_divine_intervention,
    )

    being = performance.rite.being
    sheet = performance.character_sheet
    if miracle.being_id != being.pk or not miracle.is_active:
        raise StewardAnswerError(MSG_NOT_A_MIRACLE)
    reason = miracle_ineligibility(sheet, miracle)
    if reason:
        raise StewardAnswerError(reason)
    _lock_and_resolve(prompt, resolver=resolver, note=NOTE_MIRACLE)
    done = None
    try:
        done = perform_divine_intervention(
            sheet,
            being,
            miracle,
            scene=prompt.scene,
            trigger_event="live_rite",
        )
    finally:
        if done is None:  # it raised: the GM may choose again
            _reopen(prompt)
    return LiveSend(being=being, sheet=sheet, miracle=miracle, performance=done)


def dismiss_live_prompt(prompt: GMPrompt, *, resolver: AccountDB | None, note: str) -> None:
    """Close a live prompt unanswered: nothing is sent, the rite's award stands."""
    from world.gm.constants import GMPromptStatus  # noqa: PLC0415
    from world.gm.models import GMPrompt as GMPromptModel  # noqa: PLC0415

    _live_prompt_performance(prompt)
    with transaction.atomic():
        current = (
            GMPromptModel.objects.select_for_update()
            .filter(pk=prompt.pk)
            .values_list("status", flat=True)
            .first()
        )
        if current != GMPromptStatus.PENDING:
            prompt.status = current or prompt.status
            raise StewardAnswerError(MSG_NOT_PENDING)
        prompt.status = GMPromptStatus.DISMISSED
        prompt.resolved_by = resolver
        prompt.resolution_note = note
        prompt.save(update_fields=["status", "resolved_by", "resolution_note"])


__all__ = [
    "dismiss_live_prompt",
    "is_live_prompt",
    "live_answer_options",
    "live_answers_this_week",
    "live_limit_reason",
    "live_miracle_options",
    "live_panel",
    "may_adapt_answers",
    "route_live_answer",
    "send_live_answer",
]
