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
from world.magic.types.tradition_teaching import (
    MentorShortfall,
    TeachingContext,
    TrainingVerdict,
)
from world.skills.models import Skill, Specialization
from world.traits.models import TraitCategory

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona

__all__ = [
    "MentorShortfall",
    "TeachingContext",
    "TrainingVerdict",
    "build_outsider_context",
    "build_teaching_context",
    "is_outsider",
    "is_tradition_governed",
    "mentor_acceptance_refusal",
    "mentor_shortfall",
    "taught_affinity_skill_filter",
    "taught_affinity_skill_names_by_tradition",
    "tradition_teaches",
    "traditions_offered_in_creation",
    "training_asking_refusal",
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
MENTOR_HAS_NOT_AGREED = "{mentor} has not agreed to teach you yet."
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
    reflection = offerable.filter(affinity__name=AFFINITY_PRIMAL).values_list("name", flat=True)
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


def mentor_shortfall(
    context: TeachingContext, mentor_sheet: CharacterSheet, skill: Skill | Specialization
) -> MentorShortfall | None:
    """Why this character cannot teach a Magic skill, or None when she can (#5326).

    A skill outside the Magic category needs nothing of a mentor. Otherwise she needs an
    active Tradition, that Tradition must teach the skill (a specialization is judged on its
    parent), and she must hold a rating above 0 in it. The context must hold her sheet.
    """
    from world.skills.services import skill_rating  # noqa: PLC0415

    parent = _governing_skill(skill)
    if not _is_magic_skill(parent):
        return None
    tradition = context.tradition_of(mentor_sheet.pk)
    if tradition is None:
        return MentorShortfall.NO_TRADITION
    if not context.teaches(tradition, parent.pk):
        return MentorShortfall.DOES_NOT_TEACH
    if skill_rating(mentor_sheet, parent) <= 0:
        return MentorShortfall.NO_RATING
    return None


def mentor_acceptance_refusal(
    context: TeachingContext,
    mentor_sheet: CharacterSheet,
    skill: Skill | Specialization,
    *,
    npc_name: str | None = None,
) -> str | None:
    """The line a mentor reads when she cannot agree to teach, or None when she can (#5326).

    The facts are the mentor's own, so the line names the one that applies, unlike the
    student's weekly line. It speaks to her as "You" and "Your". For an NPC a game master
    answers for, pass ``npc_name`` and the same sentences use the name.
    """
    shortfall = mentor_shortfall(context, mentor_sheet, skill)
    if shortfall is None:
        return None
    name = _governing_skill(skill).name
    if npc_name is None:
        lines = {
            MentorShortfall.NO_TRADITION: "You belong to no Tradition.",
            MentorShortfall.DOES_NOT_TEACH: f"Your Tradition does not teach {name}.",
            MentorShortfall.NO_RATING: f"You have no rating in {name}.",
        }
    else:
        lines = {
            MentorShortfall.NO_TRADITION: f"{npc_name} belongs to no Tradition.",
            MentorShortfall.DOES_NOT_TEACH: f"{npc_name}'s Tradition does not teach {name}.",
            MentorShortfall.NO_RATING: f"{npc_name} has no rating in {name}.",
        }
    return lines[shortfall]


def training_asking_refusal(
    context: TeachingContext,
    sheet: CharacterSheet,
    skill: Skill | Specialization,
    mentor: Persona | None,
) -> str | None:
    """The line that refuses naming this mentor on this training, or None (#5326).

    Naming a mentor only asks her, so nothing about the named character is read: the student
    learns nothing about her Tradition or rating. The student is refused for no mentor on a
    Magic skill she may not teach herself (her own persona counts as no mentor), and for
    naming another character her own player plays, on any skill. ``context`` must hold the
    student's lever when she names no mentor, and both players when she names one.
    """
    parent = _governing_skill(skill)
    mentor_sheet = None if mentor is None else mentor.character_sheet
    if mentor_sheet is None or mentor_sheet.pk == sheet.pk:
        if _is_magic_skill(parent) and not context.may_teach_herself(sheet.pk):
            return NEEDS_A_TEACHER.format(skill=parent.name)
        return None
    if context.played_by_one_account(sheet.pk, mentor_sheet.pk):
        return MENTOR_IS_ANOTHER_OF_YOUR_CHARACTERS
    return None


def training_verdict(
    context: TeachingContext,
    sheet: CharacterSheet,
    skill: Skill | Specialization,
    mentor: Persona | None,
    *,
    mentor_agreed: bool,
) -> TrainingVerdict:
    """Whether ``sheet`` may train ``skill`` this week with this mentor persona.

    ``skill`` is the allocation's skill, or its specialization, which is judged on its parent
    skill. ``mentor`` is the persona the player named, or ``None`` for no mentor; the refusal
    names that persona and never the character behind it. ``mentor_agreed`` says whether she
    agreed to teach (``TrainingAllocation.mentor_accepted_at`` is set). ``context`` must hold
    the student and the mentor, their players, and the student's lever when she has no
    mentor or a mentor who has not agreed (see ``build_teaching_context``).

    A skill outside the Magic category is never refused here. For a Magic skill, a mentor who
    has not agreed counts as no mentor: the training is refused unless the student's
    self-teaching lever is positive, with the line that the mentor has not agreed yet (or, for
    no mentor at all, that the skill needs a teacher). Her own persona counts as no mentor. A
    mentor another of her own characters (one account plays both) is refused. An agreed mentor
    is refused with one line, whatever the reason, when she has no active Tradition, her
    Tradition does not teach the skill, or she holds no rating (a stored value above 0) in it:
    the line never says which, so naming a persona reveals nothing about who they are. It
    never reads whether the student is an outsider: mentoring from another Tradition carries
    no penalty. A mentor's own lever is never read.

    The refusal is ``TrainingVerdict.refusal``, the full line the player reads, to be raised
    or sent as it stands.
    """
    parent = _governing_skill(skill)
    if not _is_magic_skill(parent):
        return TrainingVerdict()
    mentor_sheet = None if mentor is None else mentor.character_sheet
    if mentor_sheet is None or mentor_sheet.pk == sheet.pk:
        if context.may_teach_herself(sheet.pk):
            return TrainingVerdict()
        return TrainingVerdict(NEEDS_A_TEACHER.format(skill=parent.name))
    if not mentor_agreed:
        if context.may_teach_herself(sheet.pk):
            return TrainingVerdict()
        return TrainingVerdict(MENTOR_HAS_NOT_AGREED.format(mentor=mentor.name))
    if context.played_by_one_account(sheet.pk, mentor_sheet.pk):
        return TrainingVerdict(MENTOR_IS_ANOTHER_OF_YOUR_CHARACTERS)
    if mentor_shortfall(context, mentor_sheet, skill) is not None:
        return TrainingVerdict(MENTOR_CANNOT_TEACH.format(mentor=mentor.name, skill=parent.name))
    return TrainingVerdict()
