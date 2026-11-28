"""Which Traditions teach which skills, and who may train a Magic skill with whom (#5326).

One rule module, so character creation, weekly training and Academy courses cannot
disagree. The rule, in play terms:

- Four kinds of skill are *governed* by a Tradition's list: an affinity's own skill
  (Reflection, Heroism, Villainy) and a fighting style's own skill. Every other skill is
  taught by any Tradition.
- Every Tradition teaches Reflection (the Primal affinity's skill, found by the Primal name
  constant, never by the skill's name). A Tradition teaches another affinity's skill only
  when staff ticked it on ``Tradition.taught_skills``. A Tradition teaches a fighting
  style's skill when it is in that style's ``CombatStyle.taught_by``.
- The Tradition's state (self-taught, teachers gone, living) is never read: the Unbound row
  is a Tradition like any other.
- No Magic skill is learned by self-study. A character trains one only with a mentor who has
  an active Tradition that teaches the skill and a rating in it, unless the self-teaching
  lever (``world.mechanics.levers.self_teaching_granted``) says she may teach herself.

Weekly training (Task B of #5326) calls ``training_verdict``; Academy courses call
``is_outsider``. Both take a ``TeachingContext`` built once by ``build_teaching_context``.
``tradition_teaches`` and ``is_tradition_governed`` answer a single question with their own
queries and are for callers that ask once (the admin's ``clean``, a menu line).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db.models import Q

from world.magic.constants import AFFINITY_PRIMAL
from world.magic.models import Affinity, CharacterTradition, Tradition
from world.magic.types.tradition_teaching import TeachingContext, TrainingVerdict
from world.skills.models import Skill, Specialization
from world.traits.models import TraitCategory

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

__all__ = [
    "TeachingContext",
    "TrainingVerdict",
    "build_teaching_context",
    "is_outsider",
    "is_tradition_governed",
    "taught_affinity_skill_filter",
    "taught_affinity_skill_names_by_tradition",
    "tradition_teaches",
    "training_verdict",
]

NEEDS_A_TEACHER = "{skill} needs a teacher. Choose a mentor whose Tradition teaches it."
MENTOR_TRADITION_DOES_NOT_TEACH = (
    "{mentor}'s Tradition does not teach {skill}. Choose a mentor whose Tradition does."
)
MENTOR_HAS_NO_TRADITION = (
    "{mentor} belongs to no Tradition. Choose a mentor whose Tradition teaches {skill}."
)
MENTOR_HAS_NO_RATING = "{mentor} has no rating in {skill}. Choose a mentor who has one."


def _governing_skill(skill: Skill | Specialization) -> Skill:
    """A specialization is judged on its parent skill; a skill on itself."""
    return skill.parent_skill if isinstance(skill, Specialization) else skill


def is_tradition_governed(skill: Skill | Specialization) -> bool:
    """Whether a Tradition's list decides who teaches the skill.

    True for an affinity's own skill and a fighting style's own skill; false for every
    other skill, which any Tradition teaches. No skill is named.
    """
    from world.covenants.models import CombatStyle  # noqa: PLC0415

    parent = _governing_skill(skill)
    return (
        Affinity.objects.filter(skill=parent).exists()
        or CombatStyle.objects.filter(skill=parent).exists()
    )


def tradition_teaches(tradition: Tradition, skill: Skill | Specialization) -> bool:
    """Whether the Tradition's teachers teach the skill. Never reads the Tradition's state.

    A skill no list governs is taught by every Tradition. Reflection (the Primal affinity's
    skill) is taught by every Tradition with no tick. Another affinity's skill needs a
    ``taught_skills`` row. A fighting style's skill needs the Tradition in the style's
    ``taught_by``.
    """
    from world.covenants.models import CombatStyle  # noqa: PLC0415

    parent = _governing_skill(skill)
    affinity = Affinity.objects.filter(skill=parent).first()
    if affinity is not None:
        if affinity.name == AFFINITY_PRIMAL:
            return True
        return tradition.taught_skills.filter(pk=parent.pk).exists()
    style = CombatStyle.objects.filter(skill=parent).first()
    if style is not None:
        return style.taught_by.filter(pk=tradition.pk).exists()
    return True


def taught_affinity_skill_filter(tradition_id: int | None) -> Q:
    """A filter over ``Skill``: not an affinity's skill, or one this Tradition teaches.

    Character creation narrows the Magic skills a draft may spend on with it. With no
    Tradition (``None``) only the skills that are no affinity's pass. It answers the same
    question as ``tradition_teaches`` for an affinity's skill, as a query.
    """
    not_an_affinity_skill = Q(affinity__isnull=True)
    if tradition_id is None:
        return not_an_affinity_skill
    ticked = Tradition.taught_skills.through.objects.filter(tradition_id=tradition_id).values(
        "skill_id"
    )
    return not_an_affinity_skill | Q(affinity__name=AFFINITY_PRIMAL) | Q(pk__in=ticked)


def taught_affinity_skill_names_by_tradition(
    tradition_ids: Iterable[int],
) -> dict[int, list[str]]:
    """The affinity skills each Tradition teaches, by name: Reflection first, then its ticks.

    The creation screen shows it as one line ("Teaches Reflection and Heroism"). Two queries
    for the whole list. A game with no Primal affinity skill linked lists no Reflection.
    """
    ids = list(tradition_ids)
    reflection = list(
        Skill.objects.filter(affinity__name=AFFINITY_PRIMAL).values_list("name", flat=True)
    )
    names: dict[int, list[str]] = {tradition_id: list(reflection) for tradition_id in ids}
    ticks = Tradition.taught_skills.through.objects.filter(tradition_id__in=ids)
    for tradition_id, skill_name in ticks.order_by("skill__name").values_list(
        "tradition_id", "skill__name"
    ):
        if skill_name not in names[tradition_id]:
            names[tradition_id].append(skill_name)
    return names


def build_teaching_context(
    sheet_ids: Iterable[int],
    *,
    lever_sheet_ids: Iterable[int] | None = None,
) -> TeachingContext:
    """Gather what the rule reads for a batch of characters.

    ``sheet_ids`` must hold every student and every mentor the context will be asked about:
    asking about a sheet outside it raises. A fixed number of queries covers the catalog and
    the active Tradition of every sheet.

    ``lever_sheet_ids`` names the sheets whose self-teaching lever is read (one modifier walk
    each, ADR-0278). Only a student with no mentor on a Magic skill needs it, so the weekly
    run passes just those. ``None`` (the default) reads it for every sheet in ``sheet_ids``,
    which is right for one allocation. Each id read must also be in ``sheet_ids``.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.covenants.models import CombatStyle  # noqa: PLC0415
    from world.mechanics.levers import self_teaching_granted  # noqa: PLC0415

    sheets = set(sheet_ids)

    governed: set[int] = set()
    universal: set[int] = set()
    for skill_id, affinity_name in Affinity.objects.filter(skill__isnull=False).values_list(
        "skill_id", "name"
    ):
        governed.add(skill_id)
        if affinity_name == AFFINITY_PRIMAL:
            universal.add(skill_id)
    governed.update(
        CombatStyle.objects.filter(skill__isnull=False).values_list("skill_id", flat=True)
    )

    taught: dict[int, set[int]] = {}
    for tradition_id, skill_id in Tradition.taught_skills.through.objects.values_list(
        "tradition_id", "skill_id"
    ):
        taught.setdefault(tradition_id, set()).add(skill_id)
    for tradition_id, skill_id in CombatStyle.taught_by.through.objects.filter(
        combatstyle__skill__isnull=False
    ).values_list("tradition_id", "combatstyle__skill_id"):
        taught.setdefault(tradition_id, set()).add(skill_id)

    active: dict[int, int | None] = dict.fromkeys(sheets)
    active.update(
        CharacterTradition.objects.filter(
            character_id__in=sheets, left_at__isnull=True
        ).values_list("character_id", "tradition_id")
    )

    to_read = sheets if lever_sheet_ids is None else set(lever_sheet_ids)
    self_teaching = frozenset(
        sheet.pk
        for sheet in CharacterSheet.objects.filter(pk__in=to_read)
        if self_teaching_granted(sheet)
    )

    return TeachingContext(
        governed_skill_ids=frozenset(governed),
        universal_skill_ids=frozenset(universal),
        taught_skill_ids_by_tradition={tid: frozenset(ids) for tid, ids in taught.items()},
        active_tradition_by_sheet=active,
        self_teaching_sheet_ids=self_teaching,
    )


def is_outsider(
    context: TeachingContext, sheet: CharacterSheet, skill: Skill | Specialization
) -> bool:
    """Whether the student's own Tradition does not teach a governed skill.

    False for any skill no list governs (nobody is an outsider for Occult). A student with no
    active Tradition is an outsider on every governed skill. Academy courses read it: an
    outsider's sessions are harder. The student must be in ``context``.
    """
    parent = _governing_skill(skill)
    if parent.pk not in context.governed_skill_ids:
        return False
    return not context.teaches(context.tradition_of(sheet.pk), parent.pk)


def _is_magic_skill(skill: Skill) -> bool:
    return skill.category == TraitCategory.MAGIC


def training_verdict(
    context: TeachingContext,
    sheet: CharacterSheet,
    skill: Skill | Specialization,
    mentor_sheet: CharacterSheet | None,
    *,
    mentor_name: str | None = None,
) -> TrainingVerdict:
    """Whether ``sheet`` may allocate weekly training on ``skill`` with this mentor.

    ``skill`` is the allocation's skill, or its specialization, which is judged on its parent
    skill. ``mentor_sheet`` is the mentor persona's character, or ``None`` for no mentor.
    ``mentor_name`` is how the refusal names the mentor; it defaults to the mentor's primary
    persona's name, so pass the persona the player chose when it is not the primary one.
    ``context`` must hold the student and the mentor (see ``build_teaching_context``).

    A skill outside the Magic category is never refused here. For a Magic skill, with no
    mentor the training is refused unless the student's self-teaching lever is positive.
    With a mentor it is refused, naming the next step, when the mentor has no active
    Tradition, when the mentor's Tradition does not teach the skill, or when the mentor holds
    no rating (a stored value above 0) in it. It never reads whether the student is an
    outsider: mentoring from another Tradition carries no penalty. A mentor's own lever is
    never read.

    The refusal is ``TrainingVerdict.refusal``, the full line the player reads, to be raised
    or sent as it stands.
    """
    from world.skills.services import skill_rating  # noqa: PLC0415

    parent = _governing_skill(skill)
    if not _is_magic_skill(parent):
        return TrainingVerdict()
    if mentor_sheet is None:
        if sheet.pk in context.self_teaching_sheet_ids:
            return TrainingVerdict()
        return TrainingVerdict(NEEDS_A_TEACHER.format(skill=parent.name))
    name = mentor_name if mentor_name is not None else mentor_sheet.primary_persona.name
    mentor_tradition = context.tradition_of(mentor_sheet.pk)
    if mentor_tradition is None:
        return TrainingVerdict(MENTOR_HAS_NO_TRADITION.format(mentor=name, skill=parent.name))
    if not context.teaches(mentor_tradition, parent.pk):
        return TrainingVerdict(
            MENTOR_TRADITION_DOES_NOT_TEACH.format(mentor=name, skill=parent.name)
        )
    if skill_rating(mentor_sheet, parent) <= 0:
        return TrainingVerdict(MENTOR_HAS_NO_RATING.format(mentor=name, skill=parent.name))
    return TrainingVerdict()
