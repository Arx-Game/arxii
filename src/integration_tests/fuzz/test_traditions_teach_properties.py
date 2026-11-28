"""Fuzz: which Traditions teach Reflection, Heroism and Villainy, as properties (#5326).

Staff tick, on each Tradition, whether its teachers teach Heroism and Villainy; every
Tradition teaches Reflection with no tick. Character creation then offers a draft only the
affinity skills its own Tradition teaches. Each test below holds one rule of that design,
quoted in the maintainer's words from the issue, or named as the agreed inference or
implementer call it tests. Every example builds its rows fresh with factories and uses our
own functions (``tradition_teaches``, ``build_teaching_context``, ``training_skills``,
``reconcile_magic_training`` and the Gift-stage allocation check); the shared catalog lives
once in ``setUpTestData`` (a Hypothesis test's own ``setUp`` runs outside any transaction, so
it would leak rows between examples).

``_World`` holds the catalog: the three affinities each linked to a skill, two ordinary Magic
skills no list governs, one fighting style with its own skill, and the pool rule's one
distinction effect, which gives a draft ten points of magical training per rank held.

The second half of the file (``_TrainingWorld`` and after) holds the rules of weekly training and
Academy courses: who may train a Magic skill with whom, what an outsider's course session rolls
at, and what the weekly run does with an allocation the rule no longer allows. They call
``create_training_allocation``, ``process_weekly_training``, ``join_tradition`` and the course
handler's own session functions. The one thing a property patches is the session's check roll
(``perform_check_with_modifiers``), only to read the difficulty it was asked to roll at.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from hypothesis import given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from world.action_points.models import ActionPointPool
from world.character_creation.constants import (
    CG_MODIFIER_CATEGORY,
    MAGIC_TRAINING_POINTS_TARGET,
    TraditionState,
)
from world.character_creation.factories import (
    BeginningTraditionFactory,
    CharacterDraftFactory,
)
from world.character_creation.magic_training import reconcile_magic_training, training_skills
from world.character_creation.validators import (
    _magic_skill_allocation_errors,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.checks.services import difficulty_points
from world.classes.factories import CharacterClassLevelFactory
from world.covenants.factories import CombatStyleFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.game_clock.week_services import get_current_game_week
from world.magic.constants import AFFINITY_ABYSSAL, AFFINITY_CELESTIAL, AFFINITY_PRIMAL
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTraditionFactory,
    GiftFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
    ensure_conversion_pairs,
)
from world.magic.models import Affinity, Tradition
from world.magic.services.teaching_fit import get_teaching_config
from world.magic.services.tradition_membership import join_tradition, leave_tradition
from world.magic.services.tradition_teaching import (
    build_teaching_context,
    is_outsider,
    is_tradition_governed,
    taught_affinity_skill_names_by_tradition,
    tradition_teaches,
)
from world.mechanics.constants import (
    INCOME_CATEGORY_NAME,
    INCOME_TARGET_NAME,
    SELF_TEACHING_CATEGORY_NAME,
    SELF_TEACHING_TARGET_NAME,
)
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.test_helpers import grant_lever, lever_target
from world.narrative.models import NarrativeMessageDelivery
from world.npc_services.constants import OfferKind
from world.npc_services.effects import (
    _CourseRefusedError,
    _refuse_closed_course,
    _run_course_session,
    _take_course_session,
)
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    SkillCourseEnrollmentFactory,
    SkillCourseOfferDetailsFactory,
)
from world.npc_services.models import SkillCourseOfferDetails
from world.npc_services.services import OUTSIDER_LINE, _offer_price_payload
from world.progression.models.rewards import DevelopmentPoints
from world.roster.factories import RosterEntryFactory
from world.skills.factories import (
    MagicSkillFactory,
    SkillFactory,
    SkillPointBudgetFactory,
    SpecializationFactory,
)
from world.skills.models import Skill, TrainingAllocation
from world.skills.services import (
    calculate_training_development,
    create_training_allocation,
    process_weekly_training,
)
from world.societies.factories import OrganizationFactory
from world.traits.factories import ensure_level_ladder
from world.traits.models import CharacterTraitValue

# The two skills a Tradition may tick, by the affinity each belongs to.
TICKABLE = ("heroism", "villainy")
ticks = st.sets(st.sampled_from(TICKABLE))
states = st.sampled_from(list(TraditionState))


class _World:
    """The shared catalog for the properties below (a mixin for the test classes)."""

    @classmethod
    def setUpTestData(cls) -> None:
        celestial, primal, abyssal = ensure_conversion_pairs()
        cls.skills: dict[str, Skill] = {}
        for key, affinity, skill_name in (
            ("heroism", celestial, "Heroism"),
            ("reflection", primal, "Reflection"),
            ("villainy", abyssal, "Villainy"),
        ):
            skill = MagicSkillFactory(name=skill_name)
            affinity.skill = skill
            affinity.save()
            cls.skills[key] = skill
        Affinity.objects.clear_cache()
        assert {a.name for a in (celestial, primal, abyssal)} == {
            AFFINITY_CELESTIAL,
            AFFINITY_PRIMAL,
            AFFINITY_ABYSSAL,
        }
        cls.ordinary = [MagicSkillFactory(name="Occult"), MagicSkillFactory(name="Divination")]
        cls.style = CombatStyleFactory(skill=MagicSkillFactory(name="Duelist's Footwork"))
        SkillPointBudgetFactory(pk=1)
        target = ModifierTargetFactory(
            name=MAGIC_TRAINING_POINTS_TARGET,
            category=ModifierCategoryFactory(name=CG_MODIFIER_CATEGORY),
        )
        cls.training = DistinctionFactory(name="Tradition Training", max_rank=10)
        DistinctionEffectFactory(distinction=cls.training, target=target, value_per_rank=10)

    # -- builders ---------------------------------------------------------------------

    def tradition(self, ticked: set[str], state: str | None = None) -> Tradition:
        """A Tradition teaching the ticked skills, on a Beginning's slate in ``state``."""
        tradition = TraditionFactory()
        tradition.taught_skills.set([self.skills[key] for key in ticked])
        if state is not None:
            BeginningTraditionFactory(tradition=tradition, state=state)
        return tradition

    def draft(self, tradition: Tradition | None, *, rank: int = 0, allocation=None):
        """A draft of ``tradition`` holding the training distinction at ``rank`` (0: none)."""
        data: dict = {}
        if rank:
            data["distinctions"] = [{"distinction_id": self.training.pk, "rank": rank}]
        if allocation is not None:
            data["magic_skills"] = allocation
        return CharacterDraftFactory(draft_data=data, selected_tradition=tradition)

    def offered(self, draft) -> set[int]:
        return set(training_skills(draft).values_list("pk", flat=True))


class EveryTraditionTeachesReflection(_World, HypothesisTestCase):
    @settings(max_examples=20, deadline=None)
    @given(ticked=ticks, state=states)
    def test_reflection_is_taught_whatever_was_ticked_and_whatever_the_state(
        self, ticked: set[str], state: str
    ) -> None:
        """Maintainer: "All would teach Reflection".

        Given any Tradition, whichever of Heroism and Villainy staff ticked on it (none, one
        or both) and whichever state its slate line carries (self-taught, teachers gone or
        living): it teaches Reflection, through the one-question rule and through the
        batched context alike, and a draft of it is offered Reflection in creation.
        """
        tradition = self.tradition(ticked, state)
        reflection = self.skills["reflection"]

        self.assertTrue(tradition_teaches(tradition, reflection))
        sheet = CharacterSheetFactory()
        CharacterTraditionFactory(character=sheet, tradition=tradition)
        context = build_teaching_context([sheet.pk])
        self.assertTrue(context.teaches(tradition.pk, reflection.pk))
        self.assertFalse(is_outsider(context, sheet, reflection))
        self.assertIn(reflection.pk, self.offered(self.draft(tradition)))
        self.assertIn(
            "Reflection", taught_affinity_skill_names_by_tradition([tradition.pk])[tradition.pk]
        )


class TraditionsTeachWhatStaffTicked(_World, HypothesisTestCase):
    @settings(max_examples=25, deadline=None)
    @given(ticked=ticks, state=states, has_tradition=st.booleans(), left=st.booleans())
    def test_heroism_and_villainy_are_taught_exactly_when_ticked(
        self, ticked: set[str], state: str, has_tradition: bool, left: bool
    ) -> None:
        """Maintainer: "restrict those to Traditions that are clearly Good/Evil, while
        neutral-ish ones *might* teach all".

        Given any Tradition and any choice of ticks: it teaches Heroism exactly when staff
        ticked Heroism and Villainy exactly when they ticked Villainy, and the two answers
        agree between the one-question rule and the batched context. A teacher with no
        active Tradition (none at all, or one she left) teaches neither, and a skill no list
        governs (Occult and its kind) is taught by every Tradition and makes nobody an
        outsider.
        """
        tradition = self.tradition(ticked, state)
        sheet = CharacterSheetFactory()
        if has_tradition:
            row = CharacterTraditionFactory(character=sheet, tradition=tradition)
            if left:
                row.left_at = row.acquired_at
                row.save()
        in_a_tradition = has_tradition and not left
        context = build_teaching_context([sheet.pk])

        for key in TICKABLE:
            skill = self.skills[key]
            self.assertEqual(tradition_teaches(tradition, skill), key in ticked)
            self.assertEqual(context.teaches(tradition.pk, skill.pk), key in ticked)
            self.assertEqual(
                context.teaches(context.tradition_of(sheet.pk), skill.pk),
                in_a_tradition and key in ticked,
            )
            self.assertEqual(
                is_outsider(context, sheet, skill), not (in_a_tradition and key in ticked)
            )
        for skill in self.ordinary:
            self.assertFalse(is_tradition_governed(skill))
            self.assertTrue(tradition_teaches(tradition, skill))
            self.assertFalse(is_outsider(context, sheet, skill))


class CreationOffersWhatTheTraditionTeaches(_World, HypothesisTestCase):
    @settings(max_examples=25, deadline=None)
    @given(ticked=ticks, picked=st.booleans())
    def test_a_draft_is_offered_exactly_the_affinity_skills_its_tradition_teaches(
        self, ticked: set[str], picked: bool
    ) -> None:
        """Agreed inference: in creation she is offered only the skills her own Tradition
        teaches.

        Given any Tradition (or none picked): the affinity skills a draft is offered are
        Reflection plus the ticked ones, and none at all with no Tradition; the ordinary
        Magic skills are offered whatever the pick; another style's skill is never offered.
        """
        tradition = self.tradition(ticked) if picked else None
        offered = self.offered(self.draft(tradition))

        expected_affinity = (
            {self.skills["reflection"].pk} | {self.skills[key].pk for key in ticked}
            if picked
            else set()
        )
        affinity_ids = {skill.pk for skill in self.skills.values()}
        self.assertEqual(offered & affinity_ids, expected_affinity)
        self.assertTrue({skill.pk for skill in self.ordinary} <= offered)
        self.assertNotIn(self.style.skill_id, offered)

    @settings(max_examples=25, deadline=None)
    @given(old=ticks, new=ticks, held=st.booleans())
    def test_switching_tradition_drops_points_on_a_skill_the_new_one_does_not_teach(
        self, old: set[str], new: set[str], held: bool
    ) -> None:
        """Agreed inference: in creation she is offered only the skills her own Tradition
        teaches, so a switch takes the points off a skill the new Tradition does not teach.

        Given a draft with points on every skill its first Tradition offered, then a switch
        to a second Tradition (or to none): after the reconcile the allocation holds exactly
        the skills both Traditions offered, with their points unchanged.
        """
        first = self.tradition(old)
        draft = self.draft(first)
        offered_before = self.offered(draft)
        draft.draft_data["magic_skills"] = {str(pk): 10 for pk in offered_before}
        draft.save()

        draft.selected_tradition = self.tradition(new) if held else None
        draft.save()
        reconcile_magic_training(draft)

        kept = {int(key): value for key, value in draft.draft_data["magic_skills"].items()}
        self.assertEqual(set(kept), offered_before & self.offered(draft))
        self.assertTrue(all(value == 10 for value in kept.values()))

    @settings(max_examples=30, deadline=None)
    @given(ticked=ticks, picked=st.booleans(), rank=st.integers(0, 10))
    def test_a_draft_that_spends_its_required_spend_on_the_offered_skills_can_finish(
        self, ticked: set[str], picked: bool, rank: int
    ) -> None:
        """Agreed inference: in creation she is offered only the skills her own Tradition
        teaches, and the draft can always be finished.

        Given any Tradition (or none), any pool from 0 to 100 points: the required spend is
        no more than the pool and no more than the offered skills can hold, and a draft that
        spreads exactly its required spend across the offered skills, as much as a skill
        holds first, has no allocation error at the Gift stage.
        """
        tradition = self.tradition(ticked) if picked else None
        draft = self.draft(tradition, rank=rank)
        pool = draft.magic_training_pool
        offered = sorted(self.offered(draft))
        maximum = 30  # SkillPointBudgetFactory.max_skill_value

        self.assertLessEqual(pool.required_spend, pool.total)
        self.assertLessEqual(pool.required_spend, len(offered) * maximum)
        remaining = pool.required_spend
        allocation: dict[str, int] = {}
        for pk in offered:
            give = min(maximum, remaining)
            if give:
                allocation[str(pk)] = give
                remaining -= give
        draft.draft_data["magic_skills"] = allocation
        draft.save()

        self.assertEqual(remaining, 0)
        self.assertEqual(_magic_skill_allocation_errors(draft), [])


class NoStateIsSpecialCased(_World, HypothesisTestCase):
    @settings(max_examples=20, deadline=None)
    @given(ticked=ticks)
    def test_three_states_with_the_same_ticks_are_offered_and_teach_the_same(
        self, ticked: set[str]
    ) -> None:
        """Implementer call 14: the self-taught and teachers-gone Traditions get no special
        case.

        Given a self-taught, a teachers-gone and a living Tradition with the same ticks:
        creation offers a draft of each the same skills, and each teaches every skill the
        game governs identically, so the rule never reads a Tradition's state.
        """
        traditions = [self.tradition(ticked, state) for state in TraditionState]
        governed = [*self.skills.values(), self.style.skill]

        offered = {frozenset(self.offered(self.draft(t))) for t in traditions}
        taught = {tuple(tradition_teaches(t, skill) for skill in governed) for t in traditions}

        self.assertEqual(len(offered), 1)
        self.assertEqual(len(taught), 1)


# ---------------------------------------------------------------------------------------
# Weekly training and Academy courses
# ---------------------------------------------------------------------------------------

# The skills a rule can govern or leave alone: Reflection (taught by every Tradition), Heroism
# and Villainy (taught when ticked), a fighting style's skill (taught when the Tradition is in
# the style's ``taught_by``), and an ordinary Magic skill no list governs.
SKILL_KEYS = ("heroism", "villainy", "reflection", "style", "occult")
GOVERNED_KEYS = ("heroism", "villainy", "reflection", "style")
SIX_SKILLS = (*SKILL_KEYS, "specialization")
skill_keys = st.sampled_from(SKILL_KEYS)
governed_keys = st.sampled_from(GOVERNED_KEYS)
flags = st.booleans()


def expected_teaches(key: str, ticked: set[str], style_taught: bool) -> bool:
    """What a Tradition with these ticks teaches, written from the design and not the code.

    Reflection is taught by every Tradition with no tick; Heroism and Villainy exactly when
    staff ticked them; a fighting style's skill when the Tradition is one of the style's
    teachers; every other Magic skill by every Tradition.
    """
    if key in TICKABLE:
        return key in ticked
    if key == "style":
        return style_taught
    return True


class _TrainingWorld(_World):
    """The catalog and builders the weekly training and course properties share."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        ensure_level_ladder()
        cls.mundane = SkillFactory(name="Archery")
        cls.week = get_current_game_week()
        # The lever's rows are authored once, so an example only grants effects on them.
        lever_target(SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME)
        lever_target(INCOME_CATEGORY_NAME, INCOME_TARGET_NAME)

    # -- builders ---------------------------------------------------------------------

    def skill(self, key: str) -> Skill:
        """The catalog skill a drawn key names."""
        if key == "style":
            return self.style.skill
        if key == "occult":
            return self.ordinary[0]
        return self.skills[key]

    def teaching_tradition(self, ticked: set[str], style_taught: bool) -> Tradition:
        """A Tradition with these ticks, and listed as a teacher of the style when asked."""
        tradition = self.tradition(ticked)
        if style_taught:
            self.style.taught_by.add(tradition)
        return tradition

    def stop_teaching(self, tradition: Tradition, key: str) -> None:
        """Staff remove the tick (or the style listing) that made ``tradition`` teach ``key``."""
        if key == "style":
            self.style.taught_by.remove(tradition)
        elif key in TICKABLE:
            tradition.taught_skills.remove(self.skills[key])

    def character(
        self,
        tradition: Tradition | None = None,
        *,
        rating: int = 0,
        skill: Skill | None = None,
    ) -> CharacterSheet:
        """A character in ``tradition`` (none: no Tradition), holding ``rating`` in ``skill``."""
        sheet = CharacterSheetFactory()
        if tradition is not None:
            CharacterTraditionFactory(character=sheet, tradition=tradition)
        if rating and skill is not None:
            CharacterTraitValue.objects.create(character=sheet, trait=skill, value=rating)
        return sheet

    def allocate(self, student: CharacterSheet, skill, mentor: CharacterSheet | None) -> None:
        """Ask for one AP of weekly training, as the web action and the command do."""
        create_training_allocation(
            student.character,
            1,
            skill=skill if isinstance(skill, Skill) else None,
            specialization=None if isinstance(skill, Skill) else skill,
            mentor=None if mentor is None else mentor.primary_persona,
        )

    def stored(self, student: CharacterSheet) -> int:
        return TrainingAllocation.objects.filter(character=student).count()

    def course(
        self, trainer_tradition: Tradition | None, skill: Skill, *, saved: bool = False
    ) -> SkillCourseOfferDetails:
        """A course in ``skill`` on a trainer role of ``trainer_tradition``.

        Unsaved (``clean`` is what the admin runs) unless ``saved``. A saved course is made by
        the factory, which does not clean it: it stands for a course authored while the
        Tradition taught the skill.
        """
        role = NPCRoleFactory(teaches_tradition=trainer_tradition)
        offer = NPCServiceOfferFactory(
            role=role, kind=OfferKind.SKILL_COURSE, ap_cost=0, label=f"Course: {skill.name}"
        )
        factory = SkillCourseOfferDetailsFactory if saved else SkillCourseOfferDetailsFactory.build
        return factory(offer=offer, skill=skill, check_difficulty_level=1)

    def saved_course(
        self, trainer_tradition: Tradition | None, skill: Skill
    ) -> SkillCourseOfferDetails:
        return self.course(trainer_tradition, skill, saved=True)

    def set_extra_difficulty(self, points: int, gift_ease: int = 0) -> None:
        """The config rows are idmapper singletons: every example sets what it needs first."""
        config = get_teaching_config()
        config.other_tradition_course_difficulty = points
        config.course_ease_gift_fit = gift_ease
        config.course_ease_affinity_fit = 0
        config.save()

    def rolled_difficulty(self, course, student: CharacterSheet) -> int:
        """The difficulty one session of ``course`` rolls at for ``student``."""
        enrollment = SkillCourseEnrollmentFactory(character_sheet=student, course=course)
        result = MagicMock(outcome=None, outcome_name="Failure")
        with patch(
            "world.checks.services.perform_check_with_modifiers", return_value=result
        ) as check:
            _run_course_session(
                course.offer, course, student, enrollment, rating=0, week_pk=self.week.pk
            )
        return check.call_args.kwargs["target_difficulty"]


class CoursesAreAuthoredOnlyOnATeachingRole(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=25, deadline=None)
    @given(ticked=ticks, style_taught=flags, key=skill_keys, role_has_tradition=flags)
    def test_staff_cannot_save_a_course_the_trainers_tradition_does_not_teach(
        self, ticked: set[str], style_taught: bool, key: str, role_has_tradition: bool
    ) -> None:
        """Maintainer: "restrict those to Traditions that are clearly Good/Evil, while
        neutral-ish ones *might* teach all" (the course half of the rule).

        Given any ticks, a trainer role with or without a Tradition, and a course in any of
        Heroism, Villainy, Reflection, a fighting style's skill or an ordinary Magic skill:
        the course is refused on the Skill field exactly when the skill is one a Tradition's
        list governs and the role has no Tradition that teaches it. Heroism and Villainy on a
        role with no Tradition, or whose Tradition did not tick them, are always refused;
        Occult and its kind pass on any role.
        """
        tradition = self.teaching_tradition(ticked, style_taught) if role_has_tradition else None
        course = self.course(tradition, self.skill(key))
        governed = key in GOVERNED_KEYS
        allowed = not governed or (
            role_has_tradition and expected_teaches(key, ticked, style_taught)
        )

        if allowed:
            course.full_clean(exclude=["check_type"])
        else:
            with self.assertRaises(ValidationError) as caught:
                course.full_clean(exclude=["check_type"])
            self.assertIn("skill", caught.exception.message_dict)
            self.assertIn(course.skill.name, caught.exception.message_dict["skill"][0])


class AMentorMustTeachAndHoldARating(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=40, deadline=None)
    @given(
        ticked=ticks,
        style_taught=flags,
        key=skill_keys,
        mentor_has_tradition=flags,
        rating=st.integers(0, 3),
        student_in_tradition=flags,
    )
    def test_a_mentor_is_accepted_exactly_when_they_teach_the_skill_and_hold_a_rating(  # noqa: PLR0913 - one Hypothesis draw per argument
        self,
        ticked: set[str],
        style_taught: bool,
        key: str,
        mentor_has_tradition: bool,
        rating: int,
        student_in_tradition: bool,
    ) -> None:
        """Maintainer: "she could probably learn it from a teacher of another tradition";
        accepted default: a mentor belongs to a Tradition that teaches the skill and holds a
        rating in it.

        Given any mentor (with or without a Tradition, whatever it ticks, with a rating from
        0 to 3 in the skill) and any student (in a Tradition that teaches nothing the mentor's
        does not, or in none): the allocation is saved exactly when the mentor's active
        Tradition teaches the skill and the rating is above 0. Otherwise it raises, saves
        nothing, and the refusal names the mentor and a next step. The student's own Tradition
        changes nothing.
        """
        skill = self.skill(key)
        mentor_tradition = (
            self.teaching_tradition(ticked, style_taught) if mentor_has_tradition else None
        )
        mentor = self.character(mentor_tradition, rating=rating, skill=skill)
        student = self.character(self.tradition(set()) if student_in_tradition else None)
        accepted = (
            mentor_has_tradition and expected_teaches(key, ticked, style_taught) and rating > 0
        )

        if accepted:
            self.allocate(student, skill, mentor)
            self.assertEqual(self.stored(student), 1)
        else:
            with self.assertRaises(ValueError) as caught:
                self.allocate(student, skill, mentor)
            self.assertIn(mentor.primary_persona.name, str(caught.exception))
            self.assertIn("Choose", str(caught.exception))
            self.assertEqual(self.stored(student), 0)

    @settings(max_examples=25, deadline=None)
    @given(ticked=ticks, style_taught=flags, key=governed_keys, student_tradition=flags)
    def test_a_course_is_taken_from_a_trainer_whose_tradition_is_another_that_teaches_it(
        self, ticked: set[str], style_taught: bool, key: str, student_tradition: bool
    ) -> None:
        """Maintainer: "she could probably learn it from a teacher of another tradition".

        Given a course in a governed skill on a trainer role and a student who belongs to a
        different Tradition (or to none): enrolling is closed exactly when the trainer's
        Tradition does not teach the skill, whoever the student is, and when it is closed the
        student reads that the course is closed and what to look for.
        """
        skill = self.skill(key)
        trainer_tradition = self.teaching_tradition(ticked, style_taught)
        course = self.saved_course(trainer_tradition, skill)
        self.character(self.tradition(set()) if student_tradition else None)

        if expected_teaches(key, ticked, style_taught):
            _refuse_closed_course(course.offer, course)
        else:
            with self.assertRaises(_CourseRefusedError) as caught:
                _refuse_closed_course(course.offer, course)
            self.assertIn("this course is closed", caught.exception.reason)
            self.assertIn("Look for a trainer", caught.exception.reason)


class AnOutsiderPaysTheExtraDifficultyOnly(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=40, deadline=None)
    @given(
        key=skill_keys,
        student_ticked=ticks,
        student_style_taught=flags,
        student_in_tradition=flags,
        extra=st.integers(0, 12),
        fits=flags,
    )
    def test_a_course_session_rolls_at_the_ordinary_difficulty_plus_the_extra_points_only(  # noqa: PLR0913 - one Hypothesis draw per argument
        self,
        key: str,
        student_ticked: set[str],
        student_style_taught: bool,
        student_in_tradition: bool,
        extra: int,
        fits: bool,
    ) -> None:
        """Maintainer: "just that it might be harder"; accepted default: a student of another
        Tradition takes only the extra difficulty and keeps any fit ease.

        Given any course, any student (in a Tradition that teaches the skill or not, or in
        none), staff's extra points from 0 to 12 and a student whose Gift does or does not fit
        the trainer's Tradition (ease 2): a session rolls at the ordinary difficulty plus the
        extra points when the skill is one a Tradition's list governs and the student's own
        Tradition does not teach it, and at the ordinary difficulty otherwise; the fit ease
        comes off either way, and nothing else is added.
        """
        self.set_extra_difficulty(extra, gift_ease=2)
        skill = self.skill(key)
        trainer = self.tradition(set(TICKABLE))
        self.style.taught_by.add(trainer)
        course = self.saved_course(trainer, skill)
        student_tradition = (
            self.teaching_tradition(student_ticked, student_style_taught)
            if student_in_tradition
            else None
        )
        student = self.character(student_tradition)
        if fits:
            gift = GiftFactory()
            TraditionGiftGrantFactory(tradition=trainer, gift=gift)
            CharacterGiftFactory(character=student, gift=gift)
        outsider = key in GOVERNED_KEYS and not (
            student_in_tradition and expected_teaches(key, student_ticked, student_style_taught)
        )

        rolled = self.rolled_difficulty(course, student)

        expected = difficulty_points(1) + (extra if outsider else 0) - (2 if fits else 0)
        self.assertEqual(rolled, expected)

    @settings(max_examples=30, deadline=None)
    @given(
        key=governed_keys,
        student_ticked=ticks,
        student_style_taught=flags,
        student_in_tradition=flags,
        extra=st.integers(0, 6),
    )
    def test_the_menu_says_sessions_are_harder_exactly_for_an_outsider(
        self,
        key: str,
        student_ticked: set[str],
        student_style_taught: bool,
        student_in_tradition: bool,
        extra: int,
    ) -> None:
        """Maintainer: "just that it might be harder" (the line the student reads).

        Given a governed skill's course, any student and staff's extra points: the offer
        carries the caution line exactly when the student's own Tradition does not teach the
        skill and staff set more than 0 extra points, and carries no line otherwise.
        """
        self.set_extra_difficulty(extra)
        trainer = self.tradition(set(TICKABLE))
        self.style.taught_by.add(trainer)
        course = self.saved_course(trainer, self.skill(key))
        student_tradition = (
            self.teaching_tradition(student_ticked, student_style_taught)
            if student_in_tradition
            else None
        )
        student = self.character(student_tradition)
        outsider = not (
            student_in_tradition and expected_teaches(key, student_ticked, student_style_taught)
        )

        payload = _offer_price_payload(course.offer, student, {}, None)

        self.assertEqual(payload["outsider_line"], OUTSIDER_LINE if outsider and extra else None)

    @settings(max_examples=25, deadline=None)
    @given(
        key=governed_keys,
        first_ticks=ticks,
        second_ticks=ticks,
        student_in_tradition=flags,
        rating=st.integers(1, 5),
    )
    def test_a_mentored_week_pays_the_same_whichever_tradition_the_mentor_belongs_to(
        self,
        key: str,
        first_ticks: set[str],
        second_ticks: set[str],
        student_in_tradition: bool,
        rating: int,
    ) -> None:
        """Accepted default: weekly mentoring from another Tradition carries no penalty.

        Given two mentors of different Traditions, both teaching the skill and holding the
        same rating, and a student of any Tradition (or none) training it with each: the
        development each week pays is the same.
        """
        skill = self.skill(key)
        paid = []
        for ticked in (first_ticks | {key}, second_ticks | {key}):
            tradition = self.teaching_tradition(ticked & set(TICKABLE), key == "style")
            mentor = self.character(tradition, rating=rating, skill=skill)
            student = self.character(self.tradition(set()) if student_in_tradition else None)
            self.allocate(student, skill, mentor)
            allocation = TrainingAllocation.objects.get(character=student)
            paid.append(calculate_training_development(allocation))

        self.assertEqual(paid[0], paid[1])
        self.assertGreater(paid[0], 0)


class NoMagicalSkillIsSelfStudy(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=30, deadline=None)
    @given(key=st.sampled_from(SIX_SKILLS), student_in_tradition=flags, ticked=ticks)
    def test_a_character_with_no_lever_and_no_mentor_is_refused_every_magic_skill(
        self, key: str, student_in_tradition: bool, ticked: set[str]
    ) -> None:
        """Maintainer: "I never meant for *any* magical skill to be self-study." and "I never
        intended for fighting styles to be self-study."

        Given any student (in any Tradition, even one that teaches the skill, or in none) with
        no distinction effect on the lever, and any Magic skill (Heroism, Villainy,
        Reflection, a fighting style's skill, an ordinary Magic skill, or a specialization of
        one): asking for weekly training with no mentor is refused with the teacher line and
        nothing is saved. A skill outside the Magic category is still trained alone.
        """
        tradition = (
            self.teaching_tradition(ticked, key == "style") if student_in_tradition else None
        )
        student = self.character(tradition)
        skill = (
            SpecializationFactory(parent_skill=self.ordinary[1])
            if key == "specialization"
            else self.skill(key)
        )
        name = skill.parent_skill.name if key == "specialization" else skill.name

        with self.assertRaises(ValueError) as caught:
            self.allocate(student, skill, None)

        self.assertEqual(
            str(caught.exception),
            f"{name} needs a teacher. Choose a mentor whose Tradition teaches it.",
        )
        self.assertEqual(self.stored(student), 0)
        self.allocate(student, self.mundane, None)
        self.assertEqual(self.stored(student), 1)


class ALeverLetsHerTeachHerself(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=30, deadline=None)
    @given(
        key=st.sampled_from(SIX_SKILLS),
        value=st.integers(1, 100),
        second_source=flags,
        other_effect=flags,
    )
    def test_a_positive_lever_total_lets_her_train_alone_whatever_its_size_or_source(
        self, key: str, value: int, second_source: bool, other_effect: bool
    ) -> None:
        """Maintainer: "not unless someone has some distinction about being a magical
        prodigy/orphan".

        Given any Magic skill (a specialization included) and a distinction effect on the
        self-teaching lever worth any value from 1 to 100, with or without a second
        distinction granting it too: asking for weekly training with no mentor is saved, and
        no distinction is named by the code. A character holding a distinction whose effect
        is on another lever, however large, is refused. A larger value or a second source
        changes nothing.
        """
        skill = (
            SpecializationFactory(parent_skill=self.ordinary[1])
            if key == "specialization"
            else self.skill(key)
        )
        prodigy = self.character()
        grant_lever(prodigy, SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME, value)
        if second_source:
            grant_lever(prodigy, SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME, 1)
        ordinary = self.character()
        if other_effect:
            grant_lever(ordinary, INCOME_CATEGORY_NAME, INCOME_TARGET_NAME, value)

        self.allocate(prodigy, skill, None)
        self.assertEqual(self.stored(prodigy), 1)
        with self.assertRaises(ValueError) as caught:
            self.allocate(ordinary, skill, None)
        self.assertIn("needs a teacher", str(caught.exception))
        self.assertEqual(self.stored(ordinary), 0)


class AFormerMemberNeedsATeacher(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=30, deadline=None)
    @given(key=governed_keys, left=flags, ticked=ticks, own_ticks=ticks)
    def test_a_character_with_no_tradition_learns_a_governed_skill_only_through_a_teacher(
        self, key: str, left: bool, ticked: set[str], own_ticks: set[str]
    ) -> None:
        """Agreed inference: a character with no Tradition learns any of the three only
        through a teacher.

        Given a character with no active Tradition (never in one, or one she left, however
        much it taught) and a governed skill: training alone is refused with the teacher line,
        and training with a mentor whose Tradition teaches the skill and who holds a rating in
        it is saved.
        """
        student = self.character()
        if left:
            own = self.teaching_tradition(own_ticks | set(TICKABLE), key == "style")
            row = CharacterTraditionFactory(character=student, tradition=own)
            row.left_at = row.acquired_at
            row.save()
        skill = self.skill(key)
        mentor = self.character(
            self.teaching_tradition(ticked | ({key} & set(TICKABLE)), key == "style"),
            rating=2,
            skill=skill,
        )

        with self.assertRaises(ValueError) as caught:
            self.allocate(student, skill, None)
        self.assertIn("needs a teacher", str(caught.exception))
        self.assertEqual(self.stored(student), 0)
        self.allocate(student, skill, mentor)
        self.assertEqual(self.stored(student), 1)


class ChangingTraditionTakesNothingAway(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=25, deadline=None)
    @given(
        change=st.sampled_from(("join", "leave", "switch")),
        key=governed_keys,
        ratings=st.lists(st.integers(10, 17), min_size=4, max_size=4),
        untick=flags,
    )
    def test_joining_leaving_or_switching_keeps_every_rating_and_a_paid_course_running(
        self, change: str, key: str, ratings: list[int], untick: bool
    ) -> None:
        """Agreed inference: leaving or changing Tradition takes nothing away from what she has
        already learned.

        Given a character holding a rating and development in each of four Magic skills and
        enrolled in a course in a governed skill: after she leaves her Tradition, joins another
        (one that teaches nothing the first did not) or switches, with or without staff then
        removing the trainer's tick, every rating and every point of development is
        unchanged, and her next session of the course still runs.
        """
        skill = self.skill(key)
        held = [self.skills["heroism"], self.skills["villainy"], self.skills["reflection"], skill]
        first = self.teaching_tradition(set(TICKABLE), key == "style")
        student = self.character(first)
        for held_skill, rating in zip(held, ratings, strict=True):
            CharacterTraitValue.objects.update_or_create(
                character=student, trait=held_skill, defaults={"value": rating}
            )
            DevelopmentPoints.objects.update_or_create(
                character_sheet=student, trait=held_skill, defaults={"total_earned": rating * 3}
            )
        trainer = self.teaching_tradition(set(TICKABLE), key == "style")
        course = self.saved_course(trainer, skill)
        enrollment = SkillCourseEnrollmentFactory(character_sheet=student, course=course)
        pool = ActionPointPool.get_or_create_for_character(student.character)
        pool.current = 100
        pool.save()
        before = self.snapshot(student)

        if change == "leave":
            leave_tradition(student)
        else:
            if change == "switch":
                leave_tradition(student)
            join_tradition(student, self.tradition(set()))
        if untick:
            self.stop_teaching(trainer, key)

        self.assertEqual(self.snapshot(student), before)
        result = MagicMock(outcome=None, outcome_name="Failure")
        with patch("world.checks.services.perform_check_with_modifiers", return_value=result):
            _take_course_session(course.offer, course, student, OrganizationFactory())
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.last_session_week_id, self.week.pk)

    def snapshot(self, student: CharacterSheet) -> tuple[dict[int, int], dict[int, tuple]]:
        ratings = dict(
            CharacterTraitValue.objects.filter(character=student).values_list("trait_id", "value")
        )
        development = {
            row.trait_id: (row.total_earned, row.rust_debt)
            for row in DevelopmentPoints.objects.filter(character_sheet=student)
        }
        return ratings, development


class TheWeeklyRunSkipsWhatIsNoLongerAllowed(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=40, deadline=None)
    @given(
        key=skill_keys,
        ticked=ticks,
        style_taught=flags,
        mentored=flags,
        mentor_has_tradition=flags,
        rating=st.integers(0, 3),
        lever=flags,
    )
    def test_a_standing_allocation_no_longer_allowed_develops_nothing_and_spends_no_ap(  # noqa: PLR0913 - one Hypothesis draw per argument
        self,
        key: str,
        ticked: set[str],
        style_taught: bool,
        mentored: bool,
        mentor_has_tradition: bool,
        rating: int,
        lever: bool,
    ) -> None:
        """Implementer call 11: the weekly run skips an allocation that is no longer allowed,
        spends no action points and tells the character in one line.

        Given a standing allocation of 3 AP (saved before the rule changed, so no check
        refused it) on any Magic skill, with or without a mentor of any Tradition and rating,
        and a student with or without the self-teaching lever: after the weekly run the
        allocation is paid (the skill rises and 3 AP are spent) exactly when the rule allows
        it, with a mentor who teaches it and holds a rating, or no mentor and the lever. When
        it is not allowed the rating, the development and the AP are unchanged, the allocation
        row stays, and she is sent one line naming the skill and the refusal.
        """
        skill = self.skill(key)
        student = self.character()
        RosterEntryFactory(character_sheet=student)
        CharacterClassLevelFactory(character=student, level=1)
        CharacterTraitValue.objects.create(character=student, trait=skill, value=10)
        mentor = None
        if mentored:
            tradition = (
                self.teaching_tradition(ticked, style_taught) if mentor_has_tradition else None
            )
            mentor = self.character(tradition, rating=rating, skill=skill)
        if lever:
            grant_lever(student, SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME, 1)
        TrainingAllocation.objects.create(
            character=student,
            skill=skill,
            mentor=None if mentor is None else mentor.primary_persona,
            ap_amount=3,
        )
        pool = ActionPointPool.get_or_create_for_character(student.character)
        pool.current = 100
        pool.save()
        allowed = (
            mentor_has_tradition and expected_teaches(key, ticked, style_taught) and rating > 0
            if mentored
            else lever
        )

        process_weekly_training()

        pool.refresh_from_db()
        trained = CharacterTraitValue.objects.get(character=student, trait=skill)
        trained.refresh_from_db()
        told = NarrativeMessageDelivery.objects.filter(recipient_character_sheet=student)
        self.assertEqual(self.stored(student), 1)
        if allowed:
            self.assertGreater(trained.value, 10)
            self.assertEqual(pool.current, 97)
            self.assertEqual(told.count(), 0)
        else:
            self.assertEqual(trained.value, 10)
            self.assertFalse(DevelopmentPoints.objects.filter(character_sheet=student).exists())
            self.assertEqual(pool.current, 100)
            self.assertEqual(told.count(), 1)
            body = told.get().message.body
            self.assertIn(skill.name, body)
            self.assertIn("no action points were spent", body)
