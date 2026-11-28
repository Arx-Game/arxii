"""A mentor must agree before a mentored training counts (#5326, ADR-5326).

Naming a mentor on a training allocation only asks her. Until she agrees
(``TrainingAllocation.mentor_accepted_at`` is empty) the allocation counts as having no
mentor, everywhere: a Magic skill does not train unless the student may teach herself, and
any other skill trains as self-study without the mentor's bonus. Nothing about the named
character is checked when she is asked, so the student learns nothing about her.

This module owns the asking, the three answers (accept, decline, stop) and the one rule for
who may answer for a mentor, so the telnet command, the REST endpoints and the weekly run
cannot disagree.

Who may answer for a mentor: the account that plays her character now (the borrower of a
lent NPC, else the holder of its tenure, so a game master who holds an NPC answers for it),
or, when nobody plays her, the account that created her roster entry. Staff may always
answer. The account that plays the student never may.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.roster.models import RosterEntry
from world.roster.services.npc_lending import current_player_ids
from world.skills.models import TrainingAllocation

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.skills.models import Skill, Specialization

__all__ = [
    "MentoringError",
    "MentoringOutcome",
    "MentoringRow",
    "MentoringRows",
    "accept_mentoring",
    "answerable_allocation_ids",
    "ask_mentor",
    "decline_mentoring",
    "mentor_has_agreed",
    "mentor_is_waiting",
    "mentoring_for_account",
    "stop_mentoring",
    "tell_mentor_student_left",
]

ASKED_MENTOR_LINE = "{student} asks you to teach {pronoun} {skill}."
MENTOR_AGREED_LINE = "{mentor} agreed to teach you {skill}."
MENTOR_DECLINED_LINE = "{mentor} declined to teach you {skill}."
MENTOR_STOPPED_LINE = "{mentor} stopped teaching you {skill}."
STUDENT_LEFT_LINE = "{student} no longer trains {skill} with you."

NOT_YOURS_TO_ANSWER = "That request is not addressed to a character you can answer for."
ALREADY_AGREED = "You already agreed to teach {student} {skill}."
NOT_TEACHING = "You are not teaching {student} {skill}."


class MentoringError(ValueError):
    """A mentoring answer the rules refuse; ``user_message`` is the sentence to show."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


@dataclass(frozen=True)
class MentoringOutcome:
    """The names an answer used, captured before it cleared the mentor (#5326).

    ``mentor_name`` is the persona the student named, never the name behind it.
    """

    student_name: str
    mentor_name: str
    skill_name: str


@dataclass(frozen=True)
class MentoringRow:
    """One request or one student in an account's mentoring lists (#5326)."""

    allocation_id: int
    student_name: str
    student_pronoun: str
    mentor_name: str
    skill_name: str


@dataclass(frozen=True)
class MentoringRows:
    """Every request waiting on an account's answer and every student it teaches (#5326)."""

    requests: list[MentoringRow]
    students: list[MentoringRow]


def _target(allocation: TrainingAllocation) -> Skill | Specialization:
    return allocation.skill or allocation.specialization  # type: ignore[return-value]


def _names_a_real_mentor(allocation: TrainingAllocation) -> bool:
    """Whether the allocation names a mentor who is another character (her own is none)."""
    mentor = allocation.mentor
    return mentor is not None and mentor.character_sheet_id != allocation.character_id


def mentor_is_waiting(allocation: TrainingAllocation) -> bool:
    """Whether a mentor was named and has not agreed, so the training counts as unmentored."""
    return _names_a_real_mentor(allocation) and allocation.mentor_accepted_at is None


def mentor_has_agreed(allocation: TrainingAllocation) -> bool:
    """Whether a named mentor agreed to teach: the only state that counts as a mentor."""
    return _names_a_real_mentor(allocation) and allocation.mentor_accepted_at is not None


def _student_names(sheet_ids: Iterable[int]) -> dict[int, str]:
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    return persona_names_for_sheets(sheet_ids)


def _tell(recipient: CharacterSheet, body: str) -> None:
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    send_narrative_message(
        recipients=[recipient],
        body=body,
        category=NarrativeCategory.SYSTEM,
        sender_account=None,
    )


def _outcome(allocation: TrainingAllocation) -> MentoringOutcome:
    names = _student_names([allocation.character_id])
    return MentoringOutcome(
        student_name=names.get(allocation.character_id, allocation.character.character.key),
        mentor_name=allocation.mentor.name,
        skill_name=_target(allocation).name,
    )


def ask_mentor(allocation: TrainingAllocation) -> None:
    """Tell the named mentor's character that the student asks her to teach (#5326).

    One narrative message. Nothing about the mentor is read.
    """
    outcome = _outcome(allocation)
    pronoun = allocation.character.pronoun_object or "them"
    _tell(
        allocation.mentor.character_sheet,
        ASKED_MENTOR_LINE.format(
            student=outcome.student_name, pronoun=pronoun, skill=outcome.skill_name
        ),
    )


def tell_mentor_student_left(allocation: TrainingAllocation) -> None:
    """Tell an agreed mentor that the student no longer trains with her (#5326).

    Called before the allocation is removed or its mentor changed. A mentor who has not
    agreed is told nothing: her request just leaves her list.
    """
    if not mentor_has_agreed(allocation):
        return
    outcome = _outcome(allocation)
    _tell(
        allocation.mentor.character_sheet,
        STUDENT_LEFT_LINE.format(student=outcome.student_name, skill=outcome.skill_name),
    )


def answerable_allocation_ids(
    account: AccountDB, allocations: Sequence[TrainingAllocation]
) -> set[int]:
    """The ids of the allocations whose mentor ``account`` may answer for (#5326).

    The one rule for who answers. The account that plays the student never may; staff
    always may; otherwise the account that plays the mentor's character now, or, when nobody
    plays it, the account that created its roster entry. An allocation naming no mentor, or
    only the student's own persona, has no one to answer. Three queries however many
    allocations are asked about.
    """
    asked = [a for a in allocations if _names_a_real_mentor(a)]
    if not asked:
        return set()
    mentor_sheet_ids = {a.mentor.character_sheet_id for a in asked}
    players = current_player_ids(mentor_sheet_ids | {a.character_id for a in asked})
    unplayed = {sheet_id for sheet_id in mentor_sheet_ids if players[sheet_id] is None}
    creators: dict[int, int | None] = {}
    if unplayed and not account.is_staff:
        creators = dict(
            RosterEntry.objects.filter(character_sheet_id__in=unplayed).values_list(
                "character_sheet_id", "created_by_account_id"
            )
        )
    allowed: set[int] = set()
    for allocation in asked:
        if players[allocation.character_id] == account.pk:
            continue
        mentor_sheet_id = allocation.mentor.character_sheet_id
        mentor_player = players[mentor_sheet_id]
        if (
            account.is_staff
            or mentor_player == account.pk
            or (mentor_player is None and creators.get(mentor_sheet_id) == account.pk)
        ):
            allowed.add(allocation.pk)
    return allowed


def _require_answerer(allocation: TrainingAllocation, account: AccountDB) -> None:
    if allocation.pk not in answerable_allocation_ids(account, [allocation]):
        raise MentoringError(NOT_YOURS_TO_ANSWER)


def _require_waiting(allocation: TrainingAllocation) -> MentoringOutcome:
    outcome = _outcome(allocation)
    if allocation.mentor_accepted_at is not None:
        raise MentoringError(
            ALREADY_AGREED.format(student=outcome.student_name, skill=outcome.skill_name)
        )
    return outcome


@transaction.atomic
def accept_mentoring(allocation: TrainingAllocation, by: AccountDB) -> MentoringOutcome:
    """The mentor agrees to teach: the training counts as mentored from now (#5326).

    Checks the mentor's own facts with the Tradition rule and refuses to her, naming the
    one that applies, since they are hers: no Tradition, a Tradition that does not teach the
    skill, no rating. On success stamps the agreement and tells the student.

    Raises:
        MentoringError: ``by`` may not answer for this mentor, the request is already
            agreed, or the mentor cannot teach the skill. Nothing is saved.
    """
    from world.magic.services.tradition_teaching import (  # noqa: PLC0415
        build_outsider_context,
        mentor_acceptance_refusal,
    )
    from world.roster.services.activity import is_story_npc  # noqa: PLC0415

    _require_answerer(allocation, by)
    outcome = _require_waiting(allocation)
    mentor_sheet = allocation.mentor.character_sheet
    context = build_outsider_context([mentor_sheet.pk])
    refusal = mentor_acceptance_refusal(
        context,
        mentor_sheet,
        _target(allocation),
        npc_name=outcome.mentor_name if is_story_npc(mentor_sheet) else None,
    )
    if refusal is not None:
        raise MentoringError(refusal)
    allocation.mentor_accepted_at = timezone.now()
    allocation.save(update_fields=["mentor_accepted_at"])
    _tell(
        allocation.character,
        MENTOR_AGREED_LINE.format(mentor=outcome.mentor_name, skill=outcome.skill_name),
    )
    return outcome


@transaction.atomic
def decline_mentoring(allocation: TrainingAllocation, by: AccountDB) -> MentoringOutcome:
    """The mentor declines: the mentor is cleared from the allocation (#5326).

    The student keeps the allocation, which counts as having no mentor, and is told.

    Raises:
        MentoringError: ``by`` may not answer for this mentor, or she already agreed (she
            stops teaching instead).
    """
    _require_answerer(allocation, by)
    outcome = _require_waiting(allocation)
    allocation.mentor = None
    allocation.mentor_accepted_at = None
    allocation.save(update_fields=["mentor", "mentor_accepted_at"])
    _tell(
        allocation.character,
        MENTOR_DECLINED_LINE.format(mentor=outcome.mentor_name, skill=outcome.skill_name),
    )
    return outcome


@transaction.atomic
def stop_mentoring(allocation: TrainingAllocation, by: AccountDB) -> MentoringOutcome:
    """The mentor stops teaching: the mentor and the agreement are cleared (#5326).

    The student keeps the allocation, which counts as having no mentor, and is told. The
    student's own way to end it is to remove the allocation or change the mentor.

    Raises:
        MentoringError: ``by`` may not answer for this mentor, or she has not agreed to
            teach this student (she declines a request instead).
    """
    _require_answerer(allocation, by)
    outcome = _outcome(allocation)
    if allocation.mentor_accepted_at is None:
        raise MentoringError(
            NOT_TEACHING.format(student=outcome.student_name, skill=outcome.skill_name)
        )
    allocation.mentor = None
    allocation.mentor_accepted_at = None
    allocation.save(update_fields=["mentor", "mentor_accepted_at"])
    _tell(
        allocation.character,
        MENTOR_STOPPED_LINE.format(mentor=outcome.mentor_name, skill=outcome.skill_name),
    )
    return outcome


def mentoring_for_account(account: AccountDB) -> MentoringRows:
    """Every request waiting on ``account`` and every student it teaches (#5326).

    The list belongs to the account, not to one character: it holds the allocations of every
    character the account may answer for (``answerable_allocation_ids``), so a game master
    who holds an NPC sees that NPC's requests here. Each row names which of the account's
    characters was asked, as the student named her. Ordered by allocation id.
    """
    named = list(
        TrainingAllocation.objects.filter(mentor__isnull=False)
        .select_related(
            "character",
            "skill",
            "specialization",
            "mentor",
        )
        .order_by("pk")
    )
    allowed = answerable_allocation_ids(account, named)
    rows = [a for a in named if a.pk in allowed]
    names = _student_names({a.character_id for a in rows})
    requests: list[MentoringRow] = []
    students: list[MentoringRow] = []
    for allocation in rows:
        row = MentoringRow(
            allocation_id=allocation.pk,
            student_name=names.get(allocation.character_id, ""),
            student_pronoun=allocation.character.pronoun_object or "them",
            mentor_name=allocation.mentor.name,
            skill_name=_target(allocation).name,
        )
        (requests if allocation.mentor_accepted_at is None else students).append(row)
    return MentoringRows(requests=requests, students=students)
