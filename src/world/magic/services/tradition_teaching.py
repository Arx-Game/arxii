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
    from django.db.models import QuerySet

    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona

__all__ = [
    "TeachingContext",
    "TrainingVerdict",
    "build_outsider_context",
    "build_teaching_context",
    "is_outsider",
    "is_tradition_governed",
    "taught_affinity_skill_filter",
    "taught_affinity_skill_names_by_tradition",
    "tradition_teaches",
    "traditions_offered_in_creation",
    "training_verdict",
]

NEEDS_A_TEACHER = "{skill} needs a teacher. Choose a mentor whose Tradition teaches it."
# One line for every reason a named mentor cannot teach: no Tradition, a Tradition that does not
# teach the skill, no rating. Which of them it is would tell the asker about the character behind
# the name she typed, so the line never says (#5326).
MENTOR_CANNOT_TEACH = (
    "{mentor} cannot teach you {skill}. Choose a mentor whose Tradition teaches it and who has "
    "trained in it."
)
MENTOR_IS_ANOTHER_OF_YOUR_CHARACTERS = (
    "You cannot name another of your own characters as your mentor. "
    "Choose a mentor another player plays."
)


def _governing_skill(skill: Skill | Specialization) -> Skill:
    """A specialization is judged on its parent skill; a skill on itself."""
    return skill.parent_skill if isinstance(skill, Specialization) else skill


def is_tradition_governed(skill: Skill | Specialization) -> bool:
    """Whether a Tradition's list decides who teaches the skill.

    True for an affinity's own skill and a fighting style's own skill; false for every
    other skill, which any Tradition teaches. No skill is named. Reads the same catalog
    ``build_teaching_context`` does.
    """
    context = build_teaching_context([], lever_sheet_ids=[], player_sheet_ids=[])
    return _governing_skill(skill).pk in context.governed_skill_ids


def tradition_teaches(tradition: Tradition, skill: Skill | Specialization) -> bool:
    """Whether the Tradition's teachers teach the skill. Never reads the Tradition's state.

    The one-question form of ``TeachingContext.teaches``: it builds the catalog context and
    asks it, so it cannot differ from the batch answer. A skill no list governs is taught by
    every Tradition. Reflection (the Primal affinity's skill) is taught by every Tradition with
    no tick. Another affinity's skill needs a ``taught_skills`` row. A fighting style's skill
    needs the Tradition in the style's ``taught_by``.
    """
    context = build_teaching_context([], lever_sheet_ids=[], player_sheet_ids=[])
    return context.teaches(tradition.pk, _governing_skill(skill).pk)


def traditions_offered_in_creation() -> QuerySet[Tradition]:
    """The active Traditions some Beginning lists: the ones a new character can pick.

    The Tradition endpoint and the Required content row for Heroism and Villainy both read it,
    so what the row counts is what the endpoint can serve.
    """
    from world.character_creation.models import BeginningTradition  # noqa: PLC0415

    listed = BeginningTradition.objects.values("tradition_id")
    return Tradition.objects.filter(is_active=True, pk__in=listed)


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

    The creation screen shows it as one line ("Teaches Reflection and Heroism"). Only skills
    creation can offer count: active Magic skills that are still an affinity's skill, the same
    set ``taught_affinity_skill_filter`` lets through. Two queries for the whole list. A game
    with no Primal affinity skill linked lists no Reflection.
    """
    from world.magic.services.magic_skills import magic_category_skills  # noqa: PLC0415

    ids = list(tradition_ids)
    offerable = magic_category_skills().filter(affinity__isnull=False)
    reflection = list(
        offerable.filter(affinity__name=AFFINITY_PRIMAL).values_list("name", flat=True)
    )
    names: dict[int, list[str]] = {tradition_id: list(reflection) for tradition_id in ids}
    ticks = Tradition.taught_skills.through.objects.filter(
        tradition_id__in=ids, skill__in=offerable
    )
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
    player_sheet_ids: Iterable[int] | None = None,
) -> TeachingContext:
    """Gather what the rule reads for a batch of characters.

    ``sheet_ids`` must hold every student and every mentor the context will be asked about:
    asking about a sheet outside it raises. A fixed number of queries covers the catalog and
    the active Tradition of every sheet.

    ``lever_sheet_ids`` names the sheets whose self-teaching lever is read (one modifier walk
    each, ADR-0278). Only a student with no mentor on a Magic skill needs it, so the weekly
    run passes just those. ``player_sheet_ids`` names the sheets whose current player is read
    (two queries in all): the student and the mentor of every mentored allocation. ``None``
    (the default) reads either for every sheet in ``sheet_ids``, which is right for one
    allocation. Each id read must also be in ``sheet_ids``. A caller that never asks
    ``training_verdict`` passes ``[]`` for both, or calls ``build_outsider_context``.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.covenants.models import CombatStyle  # noqa: PLC0415
    from world.mechanics.levers import self_teaching_granted  # noqa: PLC0415
    from world.roster.services.npc_lending import current_player_ids  # noqa: PLC0415

    sheets = set(sheet_ids)

    governed: set[int] = set()
    universal: set[int] = set()
    for skill_id, affinity_name in Affinity.objects.filter(skill__isnull=False).values_list(
        "skill_id", "name"
    ):
        governed.add(skill_id)
        if affinity_name == AFFINITY_PRIMAL:
            universal.add(skill_id)
    affinity_skill_ids = set(governed)
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
        if skill_id not in affinity_skill_ids:  # an affinity's own list decides its skill
            taught.setdefault(tradition_id, set()).add(skill_id)

    active: dict[int, int | None] = dict.fromkeys(sheets)
    active.update(
        CharacterTradition.objects.filter(
            character_id__in=sheets, left_at__isnull=True
        ).values_list("character_id", "tradition_id")
    )

    lever_read = frozenset(sheets if lever_sheet_ids is None else lever_sheet_ids)
    self_teaching = frozenset(
        sheet.pk
        for sheet in CharacterSheet.objects.filter(pk__in=lever_read)
        if self_teaching_granted(sheet)
    )
    players = current_player_ids(sheets if player_sheet_ids is None else player_sheet_ids)

    return TeachingContext(
        governed_skill_ids=frozenset(governed),
        universal_skill_ids=frozenset(universal),
        taught_skill_ids_by_tradition={tid: frozenset(ids) for tid, ids in taught.items()},
        active_tradition_by_sheet=active,
        player_by_sheet=players,
        lever_read_sheet_ids=lever_read,
        self_teaching_sheet_ids=self_teaching,
    )


def build_outsider_context(sheet_ids: Iterable[int]) -> TeachingContext:
    """A context for questions about who teaches what and who is an outsider, never training.

    Reads neither the self-teaching lever nor any player, so ``training_verdict`` raises on it.
    Academy menus and courses use it.
    """
    return build_teaching_context(sheet_ids, lever_sheet_ids=[], player_sheet_ids=[])


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
    mentor: Persona | None,
) -> TrainingVerdict:
    """Whether ``sheet`` may allocate weekly training on ``skill`` with this mentor persona.

    ``skill`` is the allocation's skill, or its specialization, which is judged on its parent
    skill. ``mentor`` is the persona the player named, or ``None`` for no mentor; the refusal
    names that persona and never the character behind it. ``context`` must hold the student and
    the mentor, their players, and the student's lever when she has no mentor (see
    ``build_teaching_context``).

    A skill outside the Magic category is never refused here. For a Magic skill, with no
    mentor the training is refused unless the student's self-teaching lever is positive; her
    own persona counts as no mentor. A mentor another of her own characters (one account plays
    both) is refused. Any other mentor is refused with one line, whatever the reason, when
    they have no active Tradition, their Tradition does not teach the skill, or they hold no
    rating (a stored value above 0) in it: the line never says which, so naming a persona
    reveals nothing about who they are. It never reads whether the student is an outsider:
    mentoring from another Tradition carries no penalty. A mentor's own lever is never read.

    The refusal is ``TrainingVerdict.refusal``, the full line the player reads, to be raised
    or sent as it stands.
    """
    from world.skills.services import skill_rating  # noqa: PLC0415

    parent = _governing_skill(skill)
    if not _is_magic_skill(parent):
        return TrainingVerdict()
    mentor_sheet = None if mentor is None else mentor.character_sheet
    if mentor_sheet is None or mentor_sheet.pk == sheet.pk:
        if context.may_teach_herself(sheet.pk):
            return TrainingVerdict()
        return TrainingVerdict(NEEDS_A_TEACHER.format(skill=parent.name))
    if context.played_by_one_account(sheet.pk, mentor_sheet.pk):
        return TrainingVerdict(MENTOR_IS_ANOTHER_OF_YOUR_CHARACTERS)
    mentor_tradition = context.tradition_of(mentor_sheet.pk)
    if (
        mentor_tradition is None
        or not context.teaches(mentor_tradition, parent.pk)
        or skill_rating(mentor_sheet, parent) <= 0
    ):
        return TrainingVerdict(MENTOR_CANNOT_TEACH.format(mentor=mentor.name, skill=parent.name))
    return TrainingVerdict()
