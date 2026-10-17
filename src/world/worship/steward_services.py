"""Stewarded beings (#4333 slice 4, design 5; walkthrough C).

A ``BeingSteward`` ties a being to one GM table. Staff assign it in admin; the
assignment is refused for a table whose GM is below Senior, and for a being
that shows a sign of being a god (:func:`god_signs`). The table's GM writes the
being's pledge types and answers on the table page.

* **Who may serve it** (:func:`stewarded_refusal`): only the table's active
  members can pledge to, invoke or pray to a stewarded being, and a member's
  sacrifice to it needs no shrine.
* **The close** (:func:`route_to_steward`): a closing rite that resolves a
  pledge to a stewarded being draws nothing. The table's GM gets a
  ``BEING_ANSWER`` prompt instead, unless they muted that group or play the
  character themselves, in which case the answer is drawn as for any being.
* **The steward's answer** (:func:`send_steward_answer`): an authored answer of
  the being's at or below the closing tier, or (Success and Critical Success
  only) the GM's own text with at most one clue from the being's catalogue (the
  clues its authored answers already link). Either goes out as a vision.
* **Never dropped** (:func:`dismiss_being_answer`, :func:`expire_steward_prompts`):
  a dismissed prompt, or one left past ``DevotionConfig.steward_answer_days``,
  draws an authored answer exactly as an unstewarded close does (slice 3).

A prompt is resolved under a row lock before anything is sent, so a GM's answer,
a dismissal and the timeout cannot both deliver; the vision itself goes out
after that commits, since ``send_vision`` pushes it to an online player as its
own record commits.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.db import DatabaseError, transaction
from django.db.models import Q
from django.utils import timezone

from world.worship.constants import (
    ANSWER_FACT_MIN_SUCCESS_LEVEL,
    STEWARD_ANSWER_TEXT_MAX_LENGTH,
    VISION_RESONANCE_POOL_COST,
)
from world.worship.exceptions import (
    StewardAnswerError,
    VisionPoolInsufficient,
)
from world.worship.models import Answer, BeingSteward
from world.worship.types import AnswerDelivery

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.clues.models import Clue
    from world.gm.models import GMPrompt, GMTable
    from world.traits.models import CheckOutcome
    from world.worship.models import PledgeDetails, WorshippedBeing

MSG_NOT_A_MEMBER = "{being} answers only to the members of one GM table."
MSG_NOT_PENDING = "That prompt has already been answered."
MSG_NOT_BEING_ANSWER = "That prompt is not a being's answer."
MSG_NO_PLEDGE = "That prompt's pledge is gone."
MSG_ONE_CHOICE = "Choose one of the being's answers, or write your own text."
MSG_NOT_AN_OPTION = "That answer is not one this being can send at this tier."
MSG_FREE_TEXT_TIER = "Your own text can be sent on Success and Critical Success only."
MSG_FREE_TEXT_EMPTY = "Write the text to send."
MSG_FREE_TEXT_LONG = f"An answer is at most {STEWARD_ANSWER_TEXT_MAX_LENGTH} characters."
MSG_CLUE_NOT_IN_CATALOGUE = "That clue is not one of this being's answers link."
MSG_CLUE_WITH_AUTHORED = "An authored answer carries its own clues."
MSG_POOL_SHORT = (
    "{being}'s worship pool cannot pay for a vision yet. Send one of its authored "
    "answers instead (it is held until the pool can pay), or dismiss the prompt."
)
NOTE_DISMISSED = "Dismissed: an authored answer was drawn."
NOTE_TIMED_OUT = "No answer within {days} days: an authored answer was drawn."
NOTE_AUTHORED = "Sent an authored answer."
NOTE_FREE_TEXT = "Sent the steward's own text."


# ---------------------------------------------------------------------------
# Who stewards a being, and who may serve it
# ---------------------------------------------------------------------------


def steward_of(being: WorshippedBeing) -> BeingSteward | None:
    """The table that stewards ``being``, or None for a staff-owned being."""
    return BeingSteward.objects.filter(being=being).select_related("table__gm__account").first()


def is_table_member(sheet: CharacterSheet, table: GMTable) -> bool:
    """Whether ``sheet`` is seated at ``table`` now (an active membership)."""
    from world.gm.models import GMTableMembership  # noqa: PLC0415

    return GMTableMembership.objects.filter(
        table=table, left_at__isnull=True, persona__character_sheet=sheet
    ).exists()


def stewarded_refusal(sheet: CharacterSheet, being: WorshippedBeing) -> str:
    """The player-facing reason ``sheet`` may not serve ``being``, or "".

    Only a stewarded being refuses anyone, and only those not seated at its
    table. Pledging, invoking, praying and sacrificing all ask this.
    """
    steward = steward_of(being)
    if steward is None or is_table_member(sheet, steward.table):
        return ""
    return MSG_NOT_A_MEMBER.format(being=being.name)


def stewarded_by_table_of(sheet: CharacterSheet, being: WorshippedBeing) -> bool:
    """True when ``being`` is stewarded and ``sheet`` sits at its table: such a
    being takes a sacrifice anywhere, with no shrine (design 2)."""
    steward = steward_of(being)
    return steward is not None and is_table_member(sheet, steward.table)


# ---------------------------------------------------------------------------
# The god signs (there is no god flag)
# ---------------------------------------------------------------------------


def _table_member_sheet_ids(table: GMTable) -> set[int]:
    from world.gm.models import GMTableMembership  # noqa: PLC0415

    return set(
        GMTableMembership.objects.filter(table=table, left_at__isnull=True).values_list(
            "persona__character_sheet_id", flat=True
        )
    )


def god_signs(being: WorshippedBeing, table: GMTable) -> list[str]:
    """The signs that ``being`` is a god, which no table may steward.

    A public codex entry; any character declaring it as their public faith; a
    Chosen of it who is not seated at ``table``; a temple dedicated to it. A
    secret faith is not a sign: it is hidden by design, and a table's own spirit
    may well be one.
    """
    from world.worship.models import (  # noqa: PLC0415
        DevotionStanding,
        TempleDedication,
        WorshipDeclaration,
    )

    signs: list[str] = []
    if being.codex_entry_id is not None and being.codex_entry.is_public:
        signs.append("It has a public codex entry.")
    declared = WorshipDeclaration.objects.filter(public_being=being).count()
    if declared:
        noun = "character declares" if declared == 1 else "characters declare"
        signs.append(f"{declared} {noun} it as their public faith.")
    chosen = DevotionStanding.objects.filter(
        being=being, valence__isnull=False, released_at__isnull=True
    ).exclude(character_sheet_id__in=_table_member_sheet_ids(table))
    if chosen.exists():
        signs.append("It has a Chosen who is not seated at this table.")
    if TempleDedication.objects.filter(being=being, dissolved_at__isnull=True).exists():
        signs.append("A temple is dedicated to it.")
    return signs


def table_context_line(table: GMTable, *, being: WorshippedBeing | None = None) -> str:
    """'GM level Senior GM. 4 active members. Stewards 1 other being.': what staff
    read beside a steward assignment."""
    members = len(_table_member_sheet_ids(table))
    others = BeingSteward.objects.filter(table=table)
    if being is not None:
        others = others.exclude(being=being)
    other_count = others.count()
    member_noun = "active member" if members == 1 else "active members"
    being_noun = "other being" if other_count == 1 else "other beings"
    return (
        f"GM level {table.gm.get_level_display()}. {members} {member_noun}. "
        f"Stewards {other_count} {being_noun}."
    )


def steward_refusals(being: WorshippedBeing, table: GMTable) -> list[str]:
    """Why ``table`` may not steward ``being``; empty when it may (Ruling 5)."""
    from world.gm.constants import GMLevel, GMTableStatus  # noqa: PLC0415

    refusals: list[str] = []
    if table.gm.level != GMLevel.SENIOR:
        refusals.append(
            f"The table's GM is {table.gm.get_level_display()}; a steward's GM must be "
            f"{GMLevel.SENIOR.label}."
        )
    if table.status != GMTableStatus.ACTIVE:
        refusals.append("The table is archived.")
    refusals.extend(
        f"{being.name} shows a sign of a god: {sign}" for sign in god_signs(being, table)
    )
    return refusals


# ---------------------------------------------------------------------------
# The close goes to the steward
# ---------------------------------------------------------------------------


def closing_tier(details: PledgeDetails) -> CheckOutcome | None:
    """The outcome of the closing rite that resolved ``details``."""
    performance = details.closing_performance
    return performance.outcome_tier if performance is not None else None


def route_to_steward(details: PledgeDetails) -> AnswerDelivery | None:
    """Send a resolved pledge's answer to its being's steward as a ``BEING_ANSWER``
    prompt; None when the being has no steward or its GM will not be prompted.

    The prompt is scene-less, so it follows the GM into any scene and onto the
    table page. A GM who muted the group, or who plays the character who closed,
    is not prompted (``route_narratable_event`` drops both), and the caller then
    draws the answer as for any being.
    """
    from world.gm.constants import GMPromptKind  # noqa: PLC0415
    from world.gm.prompt_services import route_narratable_event  # noqa: PLC0415
    from world.gm.types import NarratableEvent  # noqa: PLC0415

    steward = steward_of(details.pledge.being)
    if steward is None:
        return None
    prompts = route_narratable_event(
        NarratableEvent(
            kind=GMPromptKind.BEING_ANSWER,
            scene=None,
            character_sheet=details.character_sheet,
            pledge_details=details,
        ),
        candidates=[steward.table.gm.account],
    )
    if not prompts:
        return None
    return AnswerDelivery(answer=None, vision=None, held=False, awaiting_steward=True)


# ---------------------------------------------------------------------------
# What the steward may send
# ---------------------------------------------------------------------------


def _prompt_details(prompt: GMPrompt) -> PledgeDetails:
    from world.gm.constants import GMPromptKind  # noqa: PLC0415

    if prompt.kind != GMPromptKind.BEING_ANSWER:
        raise StewardAnswerError(MSG_NOT_BEING_ANSWER)
    if prompt.pledge_id is None or closing_tier(prompt.pledge) is None:
        raise StewardAnswerError(MSG_NO_PLEDGE)
    return prompt.pledge


def answer_options(details: PledgeDetails) -> list[Answer]:
    """The being's active answers a steward may send for ``details``: its pledge
    type's and the being's general ones, at or below the closing tier, highest
    tier first."""
    tier = closing_tier(details)
    if tier is None:
        return []
    pledge = details.pledge
    return list(
        Answer.objects.filter(
            being_id=pledge.being_id,
            is_active=True,
            outcome_tier__success_level__lte=tier.success_level,
        )
        .filter(Q(pledge__isnull=True) | Q(pledge=pledge))
        .select_related("outcome_tier", "pledge")
        .order_by("-outcome_tier__success_level", "pledge_id", "pk")
    )


def may_write_free_text(details: PledgeDetails) -> bool:
    """A steward writes their own text on Success and Critical Success only."""
    tier = closing_tier(details)
    return tier is not None and tier.success_level >= ANSWER_FACT_MIN_SUCCESS_LEVEL


def catalogue_clues(being: WorshippedBeing) -> list[Clue]:
    """The clues the being's authored answers already link (fact or follow-up).

    Staff create clues; a steward attaches one of these to their own text, and
    with none linked their text goes out without one.
    """
    from world.clues.models import Clue  # noqa: PLC0415

    return list(
        Clue.objects.filter(Q(answers_as_fact__being=being) | Q(answers_as_follow_up__being=being))
        .distinct()
        .order_by("name")
    )


def answer_window_ends(prompt: GMPrompt) -> datetime:
    """When an unanswered prompt falls back to an authored answer."""
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    return prompt.created_at + timedelta(days=get_devotion_config().steward_answer_days)


def prompt_summary(prompt: GMPrompt) -> str:
    """'<being> answers <name> (<tier>).': the queue's one line for the prompt."""
    from world.gm.prompt_services import prompt_subject_name  # noqa: PLC0415

    details = prompt.pledge
    tier = closing_tier(details) if details is not None else None
    if details is None or tier is None:
        return "A being's answer."
    return f"{details.pledge.being.name} answers {prompt_subject_name(prompt)} ({tier.name})."


# ---------------------------------------------------------------------------
# Resolving the prompt
# ---------------------------------------------------------------------------


def _resolve_prompt(
    prompt: GMPrompt, *, status: str, resolver: AccountDB | None, note: str
) -> None:
    """Move a PENDING prompt to ``status`` under a row lock, or refuse.

    The lock reads the database's status, never the identity map's: a second
    request (or the timeout sweep) racing this one waits, then finds it resolved.
    """
    from world.gm.constants import GMPromptStatus  # noqa: PLC0415
    from world.gm.models import GMPrompt as GMPromptModel  # noqa: PLC0415

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
        prompt.status = status
        prompt.resolved_by = resolver
        prompt.resolution_note = note
        try:
            prompt.save(update_fields=["status", "resolved_by", "resolution_note"])
        except DatabaseError:
            prompt.status = GMPromptStatus.PENDING
            prompt.resolved_by = None
            prompt.resolution_note = ""
            raise


def _validate_free_text(details: PledgeDetails, text: str, clue: Clue | None) -> str:
    if not may_write_free_text(details):
        raise StewardAnswerError(MSG_FREE_TEXT_TIER)
    words = text.strip()
    if not words:
        raise StewardAnswerError(MSG_FREE_TEXT_EMPTY)
    if len(words) > STEWARD_ANSWER_TEXT_MAX_LENGTH:
        raise StewardAnswerError(MSG_FREE_TEXT_LONG)
    being = details.pledge.being
    if clue is not None and clue.pk not in {row.pk for row in catalogue_clues(being)}:
        raise StewardAnswerError(MSG_CLUE_NOT_IN_CATALOGUE)
    if being.resonance_pool < VISION_RESONANCE_POOL_COST:
        raise StewardAnswerError(MSG_POOL_SHORT.format(being=being.name))
    return words


def _send_free_text(
    details: PledgeDetails, words: str, clue: Clue | None, *, sent_by: AccountDB | None
) -> AnswerDelivery:
    """The steward's own text as a vision from the being, naming it.

    A Codex or secret clue rides the vision's own clue slot; any other clue (a
    mission, say) is handed over after, as an answer's follow-up clue is.
    """
    from world.clues.constants import ClueTargetKind  # noqa: PLC0415
    from world.worship.answer_services import follow_up_footnote  # noqa: PLC0415
    from world.worship.prayer_services import send_vision  # noqa: PLC0415

    fact_clue = None
    handed_clue = None
    footnotes: tuple[str, ...] = ()
    if clue is not None:
        if clue.target_kind in (ClueTargetKind.CODEX, ClueTargetKind.SECRET):
            fact_clue = clue
            footnotes = (f"A clue came with it: {clue.name}.",)
        else:
            handed_clue = clue
            footnotes = (follow_up_footnote(clue),)
    sheet = details.character_sheet
    vision = send_vision(
        recipient=sheet,
        being=details.pledge.being,
        body=words,
        sent_by=sent_by,
        reveal_source=True,
        prayer=details.prayer,
        clue=fact_clue,
        footnotes=footnotes,
    )
    roster_entry = sheet.roster_entry_or_none
    if handed_clue is not None and roster_entry is not None:
        from world.clues.services import find_clue  # noqa: PLC0415

        find_clue(roster_entry, handed_clue)
    return AnswerDelivery(answer=None, vision=vision, held=False)


def send_steward_answer(
    prompt: GMPrompt,
    *,
    resolver: AccountDB | None,
    answer: Answer | None = None,
    text: str = "",
    clue: Clue | None = None,
) -> AnswerDelivery:
    """The steward answers a closed pledge: one authored answer, or their own text.

    An authored answer must be one of :func:`answer_options` and is delivered as
    slice 3 delivers a drawn one (held while the pool is short). Free text is
    allowed on Success and Critical Success only, with at most one catalogue
    clue, and needs the pool to pay now. Authorization (the addressed GM, or
    staff) is the caller's.
    """
    from world.gm.constants import GMPromptStatus  # noqa: PLC0415
    from world.worship.answer_services import (  # noqa: PLC0415
        deliver_answer,
        deliver_pledge_answer,
    )

    details = _prompt_details(prompt)
    has_text = bool(text.strip())
    if (answer is None) == (not has_text):
        raise StewardAnswerError(MSG_ONE_CHOICE)
    if answer is not None:
        if clue is not None:
            raise StewardAnswerError(MSG_CLUE_WITH_AUTHORED)
        if answer.pk not in {row.pk for row in answer_options(details)}:
            raise StewardAnswerError(MSG_NOT_AN_OPTION)
        _resolve_prompt(
            prompt, status=GMPromptStatus.CONFIRMED, resolver=resolver, note=NOTE_AUTHORED
        )
        return deliver_answer(details, answer)
    words = _validate_free_text(details, text, clue)
    _resolve_prompt(prompt, status=GMPromptStatus.CONFIRMED, resolver=resolver, note=NOTE_FREE_TEXT)
    try:
        return _send_free_text(details, words, clue, sent_by=resolver)
    except VisionPoolInsufficient:
        # The pool was spent between the check and the send: the answer is still
        # owed, so it is drawn (and held) as a dismissal would.
        return deliver_pledge_answer(details, closing_tier(details))


def dismiss_being_answer(
    prompt: GMPrompt, *, resolver: AccountDB | None, note: str = NOTE_DISMISSED
) -> AnswerDelivery:
    """Close a ``BEING_ANSWER`` prompt unanswered: the authored draw takes over.

    Dismissing never drops the answer. The being's answers are drawn for the
    closing tier exactly as for an unstewarded being, and held if the pool is
    short.
    """
    from world.gm.constants import GMPromptStatus  # noqa: PLC0415
    from world.worship.answer_services import deliver_pledge_answer  # noqa: PLC0415

    details = _prompt_details(prompt)
    _resolve_prompt(prompt, status=GMPromptStatus.DISMISSED, resolver=resolver, note=note)
    return deliver_pledge_answer(details, closing_tier(details))


def expire_steward_prompts() -> int:
    """The tick: draw an authored answer for each prompt past its window.

    The window is ``DevotionConfig.steward_answer_days`` from the prompt. A
    prompt whose pledge is gone is closed with nothing to send. Returns how many
    prompts were closed.
    """
    from world.gm.constants import GMPromptKind, GMPromptStatus  # noqa: PLC0415
    from world.gm.models import GMPrompt as GMPromptModel  # noqa: PLC0415
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    days = get_devotion_config().steward_answer_days
    cutoff = timezone.now() - timedelta(days=days)
    overdue = GMPromptModel.objects.filter(
        kind=GMPromptKind.BEING_ANSWER, status=GMPromptStatus.PENDING, created_at__lte=cutoff
    ).select_related("pledge__pledge__being", "pledge__closing_performance__outcome_tier")
    closed = 0
    for prompt in overdue:
        try:
            if prompt.pledge_id is None:
                _resolve_prompt(
                    prompt, status=GMPromptStatus.DISMISSED, resolver=None, note=MSG_NO_PLEDGE
                )
            else:
                dismiss_being_answer(prompt, resolver=None, note=NOTE_TIMED_OUT.format(days=days))
        except StewardAnswerError:  # answered or dismissed while the sweep ran
            continue
        closed += 1
    return closed
