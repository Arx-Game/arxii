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
handler's own session functions. A course session's check roll is forced to a Failure with
``force_check_outcome`` (the Academy journeys do the same), which also records the difficulty the
roll was asked to roll at.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone
from hypothesis import given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from actions.definitions.progression import ManageTrainingAction
from evennia_extensions.models import PlayerData
from web.admin.tuning import required_content as rc
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
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import CharacterClassLevelFactory
from world.covenants.factories import CombatStyleFactory
from world.currency.services import mint_favor_token
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.game_clock.week_services import get_current_game_week
from world.magic.constants import AFFINITY_ABYSSAL, AFFINITY_CELESTIAL, AFFINITY_PRIMAL
from world.magic.factories import (
    AffinityFactory,
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
    traditions_offered_in_creation,
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
from world.npc_services.services import _offer_price_payload
from world.progression.models.rewards import DevelopmentPoints
from world.roster.constants import NPCLoanStatus
from world.roster.factories import (
    NPCLoanFactory,
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.roster.services.npc_lending import current_player_ids, current_player_of
from world.scenes.factories import PersonaFactory
from world.skills.factories import (
    MagicSkillFactory,
    SkillFactory,
    SkillPointBudgetFactory,
    SpecializationFactory,
)
from world.skills.mentoring import (
    MentoringError,
    accept_mentoring,
    decline_mentoring,
    mentoring_for_account,
    stop_mentoring,
)
from world.skills.models import Skill, SkillPointBudget, TrainingAllocation
from world.skills.serializers.training import TrainingAllocationSerializer
from world.skills.services import (
    calculate_training_development,
    create_training_allocation,
    process_weekly_training,
    training_teaching_context,
    update_training_allocation,
)
from world.societies.factories import OrganizationFactory
from world.traits.factories import CheckSystemSetupFactory, ensure_level_ladder
from world.traits.models import CharacterTraitValue, CheckOutcome

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
    # The whole domain: four tick sets (none, Heroism, Villainy, both) times three states.
    @settings(max_examples=12, deadline=None)
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
        maximum = SkillPointBudget.get_active_budget().max_skill_value

        # The Gift stage's rule, in the spec's words: the player must spend all of the pool, up to
        # what the offered Magic skills can hold. The pool is the training distinction's ten
        # points per rank (no Gift is picked, so no teaching fit adds to it).
        self.assertEqual(pool.total, rank * 10)
        self.assertEqual(pool.required_spend, min(rank * 10, len(offered) * maximum))
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
    # The whole domain: four tick sets (the three states are built inside each example).
    @settings(max_examples=4, deadline=None)
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
        CheckSystemSetupFactory.create()
        cls.failure = CheckOutcome.objects.get(name="Failure")
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

    def played(self, sheet: CharacterSheet, player_data: PlayerData) -> CharacterSheet:
        """Seat ``player_data``'s account as the current player of ``sheet``."""
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=sheet), player_data=player_data
        )
        return sheet

    def told(self, sheet: CharacterSheet) -> list[str]:
        """Every narrative line sent to ``sheet``, oldest first."""
        return [
            row.message.body
            for row in NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=sheet
            ).order_by("pk")
        ]

    def standing(
        self, student: CharacterSheet, skill, mentor: CharacterSheet | None, *, agreed: bool
    ) -> TrainingAllocation:
        """A standing 3 AP allocation as it stood before a rule changed: nothing refused it.

        ``agreed`` stamps the mentor's agreement, as ``accept_mentoring`` would.
        """
        return TrainingAllocation.objects.create(
            character=student,
            skill=skill if isinstance(skill, Skill) else None,
            specialization=None if isinstance(skill, Skill) else skill,
            mentor=None if mentor is None else mentor.primary_persona,
            mentor_accepted_at=timezone.now() if agreed and mentor is not None else None,
            ap_amount=3,
        )

    def course(
        self,
        trainer_tradition: Tradition | None,
        skill: Skill,
        *,
        saved: bool = False,
        coin_cost: int = 1000,
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
        return factory(offer=offer, skill=skill, check_difficulty_level=1, coin_cost=coin_cost)

    def saved_course(
        self, trainer_tradition: Tradition | None, skill: Skill, *, coin_cost: int = 1000
    ) -> SkillCourseOfferDetails:
        return self.course(trainer_tradition, skill, saved=True, coin_cost=coin_cost)

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
        with force_check_outcome(self.failure) as capture:
            _run_course_session(
                course.offer, course, student, enrollment, rating=0, week_pk=self.week.pk
            )
        return capture.target_difficulty


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
    def test_a_mentor_can_agree_exactly_when_they_teach_the_skill_and_hold_a_rating(  # noqa: PLR0913 - one Hypothesis draw per argument
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
        rating in it. Maintainer (2026-11-28): "The mentor must agree".

        Given any mentor (with or without a Tradition, whatever it ticks, with a rating from
        0 to 3 in the skill) asked by any student (in a Tradition that teaches nothing the
        mentor's does not, or in none): the mentor's player agrees exactly when the mentor's
        active Tradition teaches the skill and the rating is above 0. The student is told she
        agreed. Otherwise the mentor reads the one fact that applies, in the second person
        ("You belong to no Tradition.", "Your Tradition does not teach <skill>.", "You have no
        rating in <skill>."), the agreement stays empty and the student is told nothing. The
        student's own Tradition changes nothing.
        """
        skill = self.skill(key)
        mentor_tradition = (
            self.teaching_tradition(ticked, style_taught) if mentor_has_tradition else None
        )
        player = PlayerDataFactory()
        mentor = self.played(self.character(mentor_tradition, rating=rating, skill=skill), player)
        student = self.character(self.tradition(set()) if student_in_tradition else None)
        self.allocate(student, skill, mentor)
        allocation = TrainingAllocation.objects.get(character=student)
        if not mentor_has_tradition:
            refusal = "You belong to no Tradition."
        elif not expected_teaches(key, ticked, style_taught):
            refusal = f"Your Tradition does not teach {skill.name}."
        elif rating <= 0:
            refusal = f"You have no rating in {skill.name}."
        else:
            refusal = None

        if refusal is None:
            accept_mentoring(allocation, player.account)
            self.assertIsNotNone(allocation.mentor_accepted_at)
            self.assertEqual(
                self.told(student),
                [f"{mentor.primary_persona.name} agreed to teach you {skill.name}."],
            )
        else:
            with self.assertRaises(MentoringError) as caught:
                accept_mentoring(allocation, player.account)
            self.assertEqual(caught.exception.user_message, refusal)
            self.assertIsNone(allocation.mentor_accepted_at)
            self.assertEqual(self.told(student), [])

    @settings(max_examples=25, deadline=None)
    @given(ticked=ticks, style_taught=flags, key=governed_keys, student_tradition=flags)
    def test_a_course_is_taken_from_a_trainer_whose_tradition_is_another_that_teaches_it(
        self, ticked: set[str], style_taught: bool, key: str, student_tradition: bool
    ) -> None:
        """Maintainer: "she could probably learn it from a teacher of another tradition".

        Given a free course in a governed skill on a trainer role and a student who belongs
        to a different Tradition (or to none), holding a Golden Hare and the action points:
        taking the course opens an enrollment exactly when the trainer's Tradition teaches
        the skill, whoever the student is. When it does not, she reads that the course is
        closed and what to look for, no enrollment opens and her Hare is not spent.
        """
        skill = self.skill(key)
        trainer_tradition = self.teaching_tradition(ticked, style_taught)
        course = self.saved_course(trainer_tradition, skill, coin_cost=0)
        student = self.character(
            self.tradition(set()) if student_tradition else None, rating=12, skill=skill
        )
        academy = OrganizationFactory()
        hare = mint_favor_token(academy, student, provenance_note="a deed for the Academy")
        pool = ActionPointPool.get_or_create_for_character(student.character)
        pool.current = 100
        pool.save()

        with force_check_outcome(self.failure):
            if expected_teaches(key, ticked, style_taught):
                _take_course_session(course.offer, course, student, academy)
                self.assertEqual(course.enrollments.count(), 1)
            else:
                with self.assertRaises(_CourseRefusedError) as caught:
                    _take_course_session(course.offer, course, student, academy)
                self.assertIn("this course is closed", caught.exception.reason)
                self.assertIn("Look for a trainer", caught.exception.reason)
                self.assertEqual(course.enrollments.count(), 0)
                hare.refresh_from_db()
                self.assertIsNone(hare.redeemed_at)


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
        trainer_ticked=ticks,
        trainer_style_taught=flags,
    )
    def test_the_menu_says_sessions_are_harder_exactly_for_an_outsider(  # noqa: PLR0913 - one Hypothesis draw per argument
        self,
        key: str,
        student_ticked: set[str],
        student_style_taught: bool,
        student_in_tradition: bool,
        extra: int,
        trainer_ticked: set[str],
        trainer_style_taught: bool,
    ) -> None:
        """Maintainer: "just that it might be harder" (the line the student reads).

        Given a governed skill's course on any trainer role (one whose Tradition may or may
        not teach the skill), any student and staff's extra points: the offer carries the
        caution line exactly when the course can be taken (the trainer's Tradition teaches
        the skill), the student's own Tradition does not teach it and staff set more than 0
        extra points, and carries no line otherwise. A course enrollment would refuse as
        closed draws no harder line: the line is for a course she can take.

        Implementer call (not the maintainer's words): with the extra difficulty at 0 the
        harder line is hidden, because nothing is harder, so no line is drawn.
        """
        self.set_extra_difficulty(extra)
        trainer = self.teaching_tradition(trainer_ticked, trainer_style_taught)
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
        open_course = expected_teaches(key, trainer_ticked, trainer_style_taught)

        payload = _offer_price_payload(course.offer, student, {}, None)

        self.assertEqual(
            payload["outsider_line"],
            "Your Tradition does not teach this. Sessions are harder for you."
            if outsider and extra and open_course
            else None,
        )

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

        Given two mentors of different Traditions, both teaching the skill, holding the same
        rating and having agreed to teach, and a student of any Tradition (or none) training it
        with each: the development each week pays is the same.
        """
        skill = self.skill(key)
        paid = []
        for ticked in (first_ticks | {key}, second_ticks | {key}):
            tradition = self.teaching_tradition(ticked & set(TICKABLE), key == "style")
            mentor = self.character(tradition, rating=rating, skill=skill)
            student = self.character(self.tradition(set()) if student_in_tradition else None)
            allocation = self.standing(student, skill, mentor, agreed=True)
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
        with force_check_outcome(self.failure):
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
        refused it) on any Magic skill, with or without a mentor of any Tradition and rating
        who agreed to teach,
        and a student with or without the self-teaching lever: after the weekly run the
        allocation is paid (the skill rises and 3 AP are spent) exactly when the rule allows
        it, with a mentor who teaches it and holds a rating, or no mentor and the lever. When
        it is not allowed the rating, the development and the AP are unchanged, the allocation
        row stays, and she is sent one line naming the skill and the same refusal the
        allocation would have been given: the teacher line with no mentor, the one mentor
        line with a mentor.
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
        self.standing(student, skill, mentor, agreed=True)
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
            refusal = (
                f"{mentor.primary_persona.name} cannot teach you {skill.name}. Choose a mentor "
                "whose Tradition teaches it and who has trained in it."
                if mentored
                else f"{skill.name} needs a teacher. Choose a mentor whose Tradition teaches it."
            )
            self.assertIn(refusal, body)


# ---------------------------------------------------------------------------------------
# One rule, one source; what the Required content rows count; who may mentor
# ---------------------------------------------------------------------------------------

tick_sets = st.frozensets(st.sampled_from(TICKABLE))
ALL_THREE = (*TICKABLE, "reflection")


class _Restoring:
    """Flip a catalog row for one example and put it back, because the idmapper keeps it."""

    def __init__(self, skills: dict[str, Skill], active: dict[str, bool]) -> None:
        self.skills = skills
        self.active = active

    def __enter__(self) -> None:
        for key, flag in self.active.items():
            self.skills[key].is_active = flag
            self.skills[key].save()

    def __exit__(self, *exc: object) -> None:
        for key in self.active:
            self.skills[key].is_active = True
            self.skills[key].save()


class OneQuestionAndTheBatchGiveOneAnswer(_World, HypothesisTestCase):
    @settings(max_examples=30, deadline=None)
    @given(ticked=ticks, style_taught=flags, also_a_style_taught=flags)
    def test_the_single_question_equals_the_batch_answer_for_every_tradition_and_skill(
        self, ticked: set[str], style_taught: bool, also_a_style_taught: bool
    ) -> None:
        """Implementer call: the rule has one source, so the admin's check, the enrollment
        check and the weekly verdict can never disagree about who teaches a skill.

        Given any Tradition and any ticks, a fighting style that names it as a teacher or
        not, and a second style whose skill is also Heroism (a row the admin refuses to
        author, built here without its checks) that names the Tradition or not: asking one
        question gives the batched context's answer for every skill. Both equal the design:
        Heroism and Villainy are taught exactly when ticked, Heroism included when a style
        also names it as its skill (the affinity's own list decides), Reflection by every
        Tradition, a style's skill when the Tradition is one of its teachers, an ordinary
        Magic skill by every Tradition. A specialization is judged on its parent skill.
        """
        tradition = self.tradition(ticked)
        if style_taught:
            self.style.taught_by.add(tradition)
        both = CombatStyleFactory(skill=self.skills["heroism"])
        if also_a_style_taught:
            both.taught_by.add(tradition)
        context = build_teaching_context([])
        design = {
            self.skills["heroism"]: "heroism" in ticked,
            self.skills["villainy"]: "villainy" in ticked,
            self.skills["reflection"]: True,
            self.style.skill: style_taught,
        }

        for skill, teaches in design.items():
            self.assertEqual(tradition_teaches(tradition, skill), teaches)
            self.assertEqual(context.teaches(tradition.pk, skill.pk), teaches)
            self.assertTrue(is_tradition_governed(skill))
            self.assertIn(skill.pk, context.governed_skill_ids)
        specialization = SpecializationFactory(parent_skill=self.skills["heroism"])
        self.assertEqual(tradition_teaches(tradition, specialization), "heroism" in ticked)
        for skill in self.ordinary:
            self.assertTrue(tradition_teaches(tradition, skill))
            self.assertTrue(context.teaches(tradition.pk, skill.pk))
            self.assertFalse(is_tradition_governed(skill))
            self.assertNotIn(skill.pk, context.governed_skill_ids)


class TheAffinitySkillsRowCountsOnlyWhatCreationCanOffer(_World, HypothesisTestCase):
    @settings(max_examples=30, deadline=None)
    @given(
        configs=st.lists(st.tuples(tick_sets, flags, flags), max_size=3),
        heroism_active=flags,
        villainy_active=flags,
    )
    def test_the_row_lists_exactly_the_skills_no_creation_pick_can_reach(
        self,
        configs: list[tuple[frozenset[str], bool, bool]],
        heroism_active: bool,
        villainy_active: bool,
    ) -> None:
        """Maintainer: "restrict those to Traditions that are clearly Good/Evil" (the row that
        says whether any Tradition can teach them).

        Given any Traditions, each ticking any of Heroism and Villainy, each active or not and
        on some Beginning's slate or not, and each skill active or not: the Required content
        row `affinity-skills-taught` lists a skill exactly when no Tradition that is active
        and on a slate ticks it or the skill is inactive. The Traditions the Tradition
        endpoint can serve are exactly the active, listed ones; and a skill the row does not
        list is offered by creation to a draft of one of them, and a skill it lists to none.
        """
        created = []
        for ticked, active, listed in configs:
            tradition = self.tradition(set(ticked))
            tradition.is_active = active
            tradition.save()
            if listed:
                BeginningTraditionFactory(tradition=tradition)
            created.append((tradition, ticked, active and listed))
        flags_by_key = {"heroism": heroism_active, "villainy": villainy_active}
        reachable = {tradition.pk for tradition, _, reached in created if reached}
        expected = {
            self.skills[key].name
            for key in TICKABLE
            if not (
                flags_by_key[key]
                and any(key in ticked for _, ticked, reached in created if reached)
            )
        }

        with _Restoring(self.skills, flags_by_key):
            result = rc._probe_affinity_skills_are_taught()
            offered_to_any = {
                pk
                for tradition in traditions_offered_in_creation()
                for pk in self.offered(self.draft(tradition))
            }

        self.assertEqual(set(result.missing), expected)
        self.assertEqual(result.present, not expected)
        self.assertEqual({t.pk for t in traditions_offered_in_creation()}, reachable)
        for key in TICKABLE:
            self.assertEqual(
                self.skills[key].pk in offered_to_any, self.skills[key].name not in expected
            )


class TheCourseRowFindsExactlyTheCoursesEnrollmentRefuses(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=25, deadline=None)
    @given(
        draws=st.lists(
            st.tuples(skill_keys, flags, tick_sets, flags, flags), min_size=1, max_size=4
        )
    )
    def test_the_row_lists_each_refused_course_on_an_active_role_and_no_other(
        self, draws: list[tuple[str, bool, frozenset[str], bool, bool]]
    ) -> None:
        """Maintainer: "restrict those to Traditions that are clearly Good/Evil, while
        neutral-ish ones *might* teach all" (the row that finds a course nobody can take).

        Given any courses (any skill, a role with a Tradition or without, any ticks, a style
        that lists the role's Tradition or not) on active or inactive roles, and a student
        holding a Golden Hare: the Required content row `courses-taught-by-their-tradition`
        lists, as "offer: role, skill", exactly the courses on an active role whose skill a
        Tradition's list governs and whose role has no Tradition teaching it. Taking each such
        course is refused as closed (inactive roles included: enrollment never checks the
        flag), and none of the others is listed.
        """
        student = self.character(rating=12, skill=self.ordinary[0])
        academy = OrganizationFactory()
        mint_favor_token(academy, student, provenance_note="a deed for the Academy")
        pool = ActionPointPool.get_or_create_for_character(student.character)
        pool.current = 100
        pool.save()
        expected = []
        closed_courses = []
        for key, has_tradition, ticked, style_taught, active in draws:
            tradition = (
                self.teaching_tradition(set(ticked), style_taught) if has_tradition else None
            )
            course = self.saved_course(tradition, self.skill(key), coin_cost=0)
            role = course.offer.role
            role.is_active = active
            role.save()
            closed = key in GOVERNED_KEYS and not (
                has_tradition and expected_teaches(key, set(ticked), style_taught)
            )
            if closed:
                closed_courses.append(course)
            if closed and active:
                expected.append(f"{course.offer.label}: {role.name}, {course.skill.name}")

        result = rc._probe_courses_taught_by_their_tradition()

        self.assertCountEqual(result.missing, expected)
        self.assertEqual(result.present, not expected)
        with force_check_outcome(self.failure):
            for course in closed_courses:
                skill_course = self.skill_of(course)
                with self.assertRaises(_CourseRefusedError) as caught:
                    _take_course_session(course.offer, course, student, academy)
                self.assertIn("this course is closed", caught.exception.reason)
                self.assertIn(skill_course.name, caught.exception.reason)

    def skill_of(self, course: SkillCourseOfferDetails) -> Skill:
        return course.skill


class TheGovernedSkillsRowFindsASkillNobodyTeaches(_World, HypothesisTestCase):
    @settings(max_examples=30, deadline=None)
    @given(
        a_ticked=tick_sets,
        a_active=flags,
        style_in_a=flags,
        odd_affinity=flags,
    )
    def test_the_row_lists_each_governed_skill_no_active_tradition_teaches(
        self, a_ticked: frozenset[str], a_active: bool, style_in_a: bool, odd_affinity: bool
    ) -> None:
        """Maintainer: "I never intended for fighting styles to be self-study" (the row that
        finds a skill nobody could teach).

        Given one Tradition, active or not, with any ticks and the fighting style's teachers
        listing it or not, a second, inactive Tradition that teaches everything, and an
        affinity whose name is not one of the three (its skill can be ticked by no one):
        the Required content row `governed-skills-taught` lists exactly the governed skills
        that no active Tradition teaches. A fighting style with no active Tradition in
        `taught_by` is listed, an unticked Heroism or Villainy is listed, and with no active
        Tradition at all every governed skill is listed, Reflection too.
        """
        tradition = self.tradition(set(a_ticked))
        tradition.is_active = a_active
        tradition.save()
        if style_in_a:
            self.style.taught_by.add(tradition)
        elsewhere = self.tradition(set(TICKABLE))
        elsewhere.is_active = False
        elsewhere.save()
        self.style.taught_by.add(elsewhere)
        odd = self.ordinary[0]
        if odd_affinity:
            AffinityFactory(name="Cinder", skill=odd)
        everything = {
            *(self.skills[key].name for key in ALL_THREE),
            self.style.skill.name,
            *([odd.name] if odd_affinity else []),
        }
        if a_active:
            expected = {self.skills[key].name for key in TICKABLE if key not in a_ticked}
            if not style_in_a:
                expected.add(self.style.skill.name)
            if odd_affinity:
                expected.add(odd.name)
        else:
            expected = everything

        result = rc._probe_governed_skills_are_taught()

        self.assertEqual(set(result.missing), expected)
        self.assertEqual(result.present, not expected)


class TheCreationCardAndListAgreeOnWhatIsTaught(_World, HypothesisTestCase):
    @settings(max_examples=30, deadline=None)
    @given(
        ticked=ticks,
        reflection_active=flags,
        heroism_active=flags,
        villainy_active=flags,
        heroism_unlinked=flags,
    )
    def test_the_card_names_exactly_the_affinity_skills_the_list_offers(
        self,
        ticked: set[str],
        reflection_active: bool,
        heroism_active: bool,
        villainy_active: bool,
        heroism_unlinked: bool,
    ) -> None:
        """Agreed inference: in creation she is offered only the skills her own Tradition
        teaches, and the card that says so names the same skills.

        Given any Tradition and any ticks, each of the three affinity skills active or not,
        and Heroism still an affinity's skill or not: the skills the Tradition entry names as
        taught are exactly the affinity skills the draft's training list offers, and they are
        Reflection and the ticked skills that are active and still an affinity's.
        """
        active = {
            "reflection": reflection_active,
            "heroism": heroism_active,
            "villainy": villainy_active,
        }
        tradition = self.tradition(ticked)
        celestial = Affinity.objects.get(name=AFFINITY_CELESTIAL)
        try:
            with _Restoring(self.skills, active):
                if heroism_unlinked:
                    celestial.skill = None
                    celestial.save()
                names = taught_affinity_skill_names_by_tradition([tradition.pk])[tradition.pk]
                offered = self.offered(self.draft(tradition))
                linked = set(
                    Affinity.objects.filter(skill__isnull=False).values_list("skill_id", flat=True)
                )
        finally:
            celestial.skill = self.skills["heroism"]
            celestial.save()
            Affinity.objects.clear_cache()

        listed = {skill.name for skill in self.skills.values() if skill.pk in offered & linked}
        taught = {
            self.skills[key].name
            for key in ("reflection", *ticked)
            if active[key] and not (key == "heroism" and heroism_unlinked)
        }
        self.assertEqual(set(names), listed)
        self.assertEqual(set(names), taught)


class ASpecializationIsJudgedOnItsParentSkill(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=40, deadline=None)
    @given(
        key=skill_keys,
        ticked=ticks,
        style_taught=flags,
        mentor_has_tradition=flags,
        rating=st.integers(0, 3),
    )
    def test_a_mentor_for_a_specialization_must_teach_and_rate_its_parent(
        self,
        key: str,
        ticked: set[str],
        style_taught: bool,
        mentor_has_tradition: bool,
        rating: int,
    ) -> None:
        """Maintainer: "I never meant for *any* magical skill to be self-study." (a
        specialization is a Magic skill's own training, so it follows its parent).

        Given a specialization of any Magic skill (Heroism, Villainy, Reflection, a fighting
        style's skill or an ordinary one) and any mentor with a rating in the parent skill
        from 0 to 3, asked to teach it: her player can agree exactly when the mentor's
        Tradition teaches the parent skill and the rating is above 0. Otherwise the refusal
        she reads names the parent skill and the agreement stays empty.
        """
        parent = self.skill(key)
        specialization = SpecializationFactory(parent_skill=parent)
        tradition = self.teaching_tradition(ticked, style_taught) if mentor_has_tradition else None
        player = PlayerDataFactory()
        mentor = self.played(self.character(tradition, rating=rating, skill=parent), player)
        student = self.character()
        self.allocate(student, specialization, mentor)
        allocation = TrainingAllocation.objects.get(character=student)
        agrees = mentor_has_tradition and expected_teaches(key, ticked, style_taught) and rating > 0

        if agrees:
            accept_mentoring(allocation, player.account)
            self.assertIsNotNone(allocation.mentor_accepted_at)
        else:
            with self.assertRaises(MentoringError) as caught:
                accept_mentoring(allocation, player.account)
            self.assertIn(
                caught.exception.user_message,
                (
                    "You belong to no Tradition.",
                    f"Your Tradition does not teach {parent.name}.",
                    f"You have no rating in {parent.name}.",
                ),
            )
            self.assertIsNone(allocation.mentor_accepted_at)


class TheWeeklyRunJudgesASpecializationOnItsParent(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=30, deadline=None)
    @given(
        key=skill_keys,
        ticked=ticks,
        style_taught=flags,
        mentored=flags,
        mentor_has_tradition=flags,
        rating=st.integers(0, 3),
        lever=flags,
    )
    def test_a_standing_specialization_allocation_runs_only_when_its_parent_is_allowed(  # noqa: PLR0913 - one Hypothesis draw per argument
        self,
        key: str,
        ticked: set[str],
        style_taught: bool,
        mentored: bool,
        mentor_has_tradition: bool,
        rating: int,
        lever: bool,
    ) -> None:
        """Implementer call 11 (the weekly run skips what is no longer allowed), for a
        specialization.

        Given a standing allocation of 3 AP on a specialization of any Magic skill, with or
        without a mentor and the self-teaching lever: after the weekly run it is paid (a
        specialization rating exists and 3 AP are spent) exactly when its parent skill would
        be allowed. Otherwise nothing is paid, no AP are spent, the row stays and she is sent
        one line naming the parent skill.
        """
        parent = self.skill(key)
        specialization = SpecializationFactory(parent_skill=parent)
        student = self.character()
        RosterEntryFactory(character_sheet=student)
        CharacterClassLevelFactory(character=student, level=1)
        CharacterTraitValue.objects.create(character=student, trait=parent, value=10)
        mentor = None
        if mentored:
            tradition = (
                self.teaching_tradition(ticked, style_taught) if mentor_has_tradition else None
            )
            mentor = self.character(tradition, rating=rating, skill=parent)
        if lever:
            grant_lever(student, SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME, 1)
        self.standing(student, specialization, mentor, agreed=True)
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
        told = NarrativeMessageDelivery.objects.filter(recipient_character_sheet=student)
        self.assertEqual(self.stored(student), 1)
        if allowed:
            self.assertEqual(pool.current, 97)
            self.assertEqual(told.count(), 0)
        else:
            self.assertEqual(pool.current, 100)
            self.assertEqual(told.count(), 1)
            self.assertIn(parent.name, told.get().message.body)


class ACharacterIsNeverHerOwnMentor(_TrainingWorld, HypothesisTestCase):
    @settings(max_examples=30, deadline=None)
    @given(
        key=skill_keys,
        who=st.sampled_from(("herself", "her own alt", "another player's character")),
        lever=flags,
    )
    def test_her_own_character_never_counts_as_a_mentor(
        self, key: str, who: str, lever: bool
    ) -> None:
        """Owner rule (a player never benefits from pairing her own characters): a character
        does not mentor herself, and neither does another character her player plays.

        Given any Magic skill, a mentor who teaches it with a rating of 2, and the student
        with or without the self-teaching lever: naming her own persona counts as naming no
        mentor (saved exactly when the lever is positive, else the teacher line); naming
        another character one account plays is refused with "You cannot name another of your
        own characters as your mentor. Choose a mentor another player plays." whatever the
        lever; naming a character another player plays is saved. A character nobody plays
        (an NPC a GM runs) is not an own character and is allowed (the other properties here
        name such mentors throughout).
        """
        skill = self.skill(key)
        teaching = self.teaching_tradition(set(TICKABLE), True)
        player = PlayerDataFactory()
        student = self.played(self.character(teaching, rating=2, skill=skill), player)
        if lever:
            grant_lever(student, SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME, 1)
        if who == "herself":
            mentor = student
        else:
            other = player if who == "her own alt" else PlayerDataFactory()
            mentor = self.played(self.character(teaching, rating=2, skill=skill), other)
        allowed = lever if who == "herself" else who == "another player's character"

        if allowed:
            self.allocate(student, skill, mentor)
            self.assertEqual(self.stored(student), 1)
        else:
            with self.assertRaises(ValueError) as caught:
                self.allocate(student, skill, mentor)
            line = (
                f"{skill.name} needs a teacher. Choose a mentor whose Tradition teaches it."
                if who == "herself"
                else "You cannot name another of your own characters as your mentor. "
                "Choose a mentor another player plays."
            )
            self.assertEqual(str(caught.exception), line)
            self.assertEqual(self.stored(student), 0)

    # The whole domain: two kinds of mentor. The skill changes only the sentence's text.
    @settings(max_examples=2, deadline=None)
    @given(who=st.sampled_from(("her own alt", "another player's character")))
    def test_the_weekly_run_skips_a_standing_allocation_naming_her_own_alt(self, who: str) -> None:
        """Owner rule (a player never benefits from pairing her own characters), for a
        standing allocation.

        Given a standing allocation of 3 AP naming a mentor who teaches the skill with a
        rating of 2 and agreed to teach, saved before the rule: after the weekly run it is
        paid when the mentor is another player's character, and when the mentor is another
        of her own it is skipped, no AP are spent, and she is sent the one own-character line.
        """
        skill = self.skill("villainy")
        teaching = self.teaching_tradition(set(TICKABLE), True)
        player = PlayerDataFactory()
        student = self.played(self.character(), player)
        CharacterClassLevelFactory(character=student, level=1)
        CharacterTraitValue.objects.create(character=student, trait=skill, value=10)
        other = player if who == "her own alt" else PlayerDataFactory()
        mentor = self.played(self.character(teaching, rating=2, skill=skill), other)
        self.standing(student, skill, mentor, agreed=True)
        pool = ActionPointPool.get_or_create_for_character(student.character)
        pool.current = 100
        pool.save()

        process_weekly_training()

        pool.refresh_from_db()
        told = NarrativeMessageDelivery.objects.filter(recipient_character_sheet=student)
        if who == "her own alt":
            self.assertEqual(pool.current, 100)
            self.assertEqual(told.count(), 1)
            self.assertIn(
                "You cannot name another of your own characters as your mentor. "
                "Choose a mentor another player plays.",
                told.get().message.body,
            )
        else:
            self.assertEqual(pool.current, 97)
            self.assertEqual(told.count(), 0)


class ARefusedMentorRevealsNothingAboutThePersona(_TrainingWorld, HypothesisTestCase):
    # The whole domain: the three reasons. The skill changes only the sentence's text.
    @settings(max_examples=3, deadline=None)
    @given(reason=st.sampled_from(("no tradition", "tradition does not teach", "no rating")))
    def test_naming_a_persona_reveals_nothing_and_the_weekly_line_names_only_it(
        self, reason: str
    ) -> None:
        """Implementer call (privacy): naming a persona must not tell the asker about the
        character behind it.

        Given a mentor behind a second persona (a mask) who cannot teach the skill for any
        one of three reasons (no active Tradition, a Tradition that does not teach it, no
        rating in it): the student naming the mask is told only that she asked, and the
        name behind the mask is nowhere in it. When that mentor had agreed before she stopped
        qualifying, the weekly run sends the one line "{mask} cannot teach you {skill}. Choose
        a mentor whose Tradition teaches it and who has trained in it." for each reason, and
        the name behind the mask is not in it.
        """
        skill = self.skill("villainy")
        if reason == "no tradition":
            tradition = None
        elif reason == "tradition does not teach":
            tradition = self.teaching_tradition(set(), False)
        else:
            tradition = self.teaching_tradition(set(TICKABLE), True)
        mentor = self.character(tradition, rating=0 if reason == "no rating" else 2, skill=skill)
        mask = PersonaFactory(character_sheet=mentor, name="The Veiled Widow")
        student = self.character()
        RosterEntryFactory(character_sheet=student)
        CharacterClassLevelFactory(character=student, level=1)
        CharacterTraitValue.objects.create(character=student, trait=skill, value=10)

        asked = ManageTrainingAction().run(
            actor=student.character,
            operation="add",
            skill_id=skill.pk,
            ap_amount=1,
            mentor_persona_id=mask.pk,
        )

        self.assertEqual(
            asked.message,
            "You ask The Veiled Widow to teach you "
            f"{skill.name}. Your training waits until The Veiled Widow agrees.",
        )
        self.assertNotIn(mentor.primary_persona.name, asked.message)
        allocation = TrainingAllocation.objects.get(character=student)
        allocation.mentor_accepted_at = timezone.now()
        allocation.save()
        pool = ActionPointPool.get_or_create_for_character(student.character)
        pool.current = 100
        pool.save()

        process_weekly_training()

        (line,) = self.told(student)
        self.assertIn(
            f"The Veiled Widow cannot teach you {skill.name}. Choose a mentor whose Tradition "
            "teaches it and who has trained in it.",
            line,
        )
        self.assertNotIn(mentor.primary_persona.name, line)


class AnEditToASavedCourseIsRefusedOnceItsTraditionStoppedTeaching(
    _TrainingWorld, HypothesisTestCase
):
    # The whole domain: three governed skills times ticked or not.
    @settings(max_examples=6, deadline=None)
    @given(key=st.sampled_from(("heroism", "villainy", "style")), untick=flags)
    def test_changing_any_field_of_a_saved_course_is_refused_on_the_skill_field(
        self, key: str, untick: bool
    ) -> None:
        """Maintainer: "restrict those to Traditions that are clearly Good/Evil, while
        neutral-ish ones *might* teach all" (a course that cannot be taught cannot be saved,
        even by an edit to something else).

        Given a course saved while its role's Tradition taught the skill, and staff then
        removing the tick (or the style listing) or not: changing only its coin cost and
        cleaning it is refused on the Skill field, naming the skill, exactly when the
        Tradition no longer teaches it.
        """
        tradition = self.teaching_tradition(set(TICKABLE), True)
        course = self.saved_course(tradition, self.skill(key))
        if untick:
            self.stop_teaching(tradition, key)
        course.coin_cost = 2500

        if untick:
            with self.assertRaises(ValidationError) as caught:
                course.full_clean(exclude=["check_type"])
            self.assertIn("skill", caught.exception.message_dict)
            self.assertIn(course.skill.name, caught.exception.message_dict["skill"][0])
        else:
            course.full_clean(exclude=["check_type"])


class ThePlayersOfManyCharactersAreTheOnesTheRuleNames(HypothesisTestCase):
    @settings(max_examples=25, deadline=None)
    @given(
        specs=st.lists(
            st.tuples(st.sampled_from(("never", "held", "ended", "held_after_ended")), flags),
            min_size=1,
            max_size=4,
        )
    )
    def test_the_bulk_reading_equals_the_one_at_a_time_reading_and_the_rule(
        self, specs: list[tuple[str, bool]]
    ) -> None:
        """Owner rule (a player never benefits from pairing her own characters): the player
        of a character is the borrower of its active loan, else the account holding its
        current tenure, else nobody.

        Given characters that were never played, are held, were held and ended, or were held
        again after an earlier tenure ended, each lent out on an active loan or not: the bulk
        reading of every character's player gives, for each, the account the rule names
        (the borrower when lent, else the current holder, else none), which is also what
        `current_player_of` answers for it.
        """
        sheets = []
        expected: dict[int, int | None] = {}
        for state, lent in specs:
            sheet = CharacterSheetFactory()
            sheets.append(sheet)
            holder = PlayerDataFactory()
            expected[sheet.pk] = None
            if state != "never" or lent:
                entry = RosterEntryFactory(character_sheet=sheet)
            if state in ("ended", "held_after_ended"):
                earlier = PlayerDataFactory()
                RosterTenureFactory(
                    roster_entry=entry,
                    player_data=earlier,
                    start_date=timezone.now() - timedelta(days=9),
                    end_date=timezone.now() - timedelta(days=5),
                )
            if state in ("held", "held_after_ended"):
                RosterTenureFactory(roster_entry=entry, player_data=holder)
                expected[sheet.pk] = holder.account_id
            if lent:
                borrower = PlayerDataFactory().account
                NPCLoanFactory(roster_entry=entry, borrower=borrower, status=NPCLoanStatus.ACTIVE)
                expected[sheet.pk] = borrower.pk

        bulk = current_player_ids([sheet.pk for sheet in sheets])

        self.assertEqual(bulk, expected)
        for sheet in sheets:
            account = current_player_of(sheet)
            self.assertEqual(None if account is None else account.pk, expected[sheet.pk])


# ---------------------------------------------------------------------------------------
# The mentor must agree (maintainer, 2026-11-28)
# ---------------------------------------------------------------------------------------


class _MentoringWorld(_TrainingWorld):
    """Builders for a student, qualified mentors who are played, and one request between them."""

    def mentor(self, key: str, player: PlayerData | None = None) -> CharacterSheet:
        """A character who teaches the skill with a rating of 2, played by ``player``."""
        skill = self.skill(key)
        sheet = self.character(self.teaching_tradition(set(TICKABLE), True), rating=2, skill=skill)
        return sheet if player is None else self.played(sheet, player)

    def asked(self, key: str, mentor: CharacterSheet) -> tuple[CharacterSheet, TrainingAllocation]:
        """A student who asked ``mentor`` to teach the skill: her row, not yet answered."""
        student = self.character()
        self.allocate(student, self.skill(key), mentor)
        return student, TrainingAllocation.objects.get(character=student)

    def staff_account(self):
        account = PlayerDataFactory().account
        account.is_staff = True
        account.save()
        return account


class AMentorWhoHasNotAgreedIsNoMentor(_MentoringWorld, HypothesisTestCase):
    @settings(max_examples=30, deadline=None)
    @given(
        key=st.sampled_from((*SKILL_KEYS, "mundane")),
        lever=flags,
        mentor_qualifies=flags,
        rating=st.integers(1, 3),
    )
    def test_a_waiting_mentor_counts_as_none_in_the_week_and_in_the_formula(
        self, key: str, lever: bool, mentor_qualifies: bool, rating: int
    ) -> None:
        """Maintainer (2026-11-28): "The mentor must agree".
        Implementer call (one rule everywhere): an allocation whose mentor has not agreed
        counts as having no mentor.

        Given a standing allocation of 3 AP naming a mentor who has not agreed, whoever she is
        (a qualified teacher or not), on any Magic skill or on a skill outside the Magic
        category, and a student with or without the self-teaching lever: the weekly run pays a
        Magic skill exactly when the student holds the lever, otherwise it skips it, spends no
        action points and sends one line "<mentor> has not agreed to teach you yet."; a skill
        outside the Magic category is paid as self-study, and its development is the base gain
        with no mentor bonus (15 for 3 AP at level 1). Once the mentor agrees, that same
        mundane allocation pays more than the base gain.
        """
        skill = self.mundane if key == "mundane" else self.skill(key)
        tradition = self.teaching_tradition(set(TICKABLE), True) if mentor_qualifies else None
        # A rating well above the student's 10, so an agreed mentor's bonus is not truncated away.
        mentor = self.character(tradition, rating=rating * 40, skill=skill)
        student = self.character()
        RosterEntryFactory(character_sheet=student)
        CharacterClassLevelFactory(character=student, level=1)
        CharacterTraitValue.objects.create(character=student, trait=skill, value=10)
        if lever:
            grant_lever(student, SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME, 1)
        allocation = self.standing(student, skill, mentor, agreed=False)
        pool = ActionPointPool.get_or_create_for_character(student.character)
        pool.current = 100
        pool.save()
        magic = key != "mundane"
        paid = lever or not magic

        process_weekly_training()

        pool.refresh_from_db()
        self.assertEqual(self.stored(student), 1)
        if paid:
            self.assertEqual(pool.current, 97)
            self.assertEqual(self.told(student), [])
        else:
            self.assertEqual(pool.current, 100)
            (line,) = self.told(student)
            self.assertIn(
                f"Your weekly training in {skill.name} did not run, and no action points were "
                f"spent. {mentor.primary_persona.name} has not agreed to teach you yet.",
                line,
            )
        if not magic:
            self.assertEqual(calculate_training_development(allocation), 15)
            allocation.mentor_accepted_at = timezone.now()
            allocation.save()
            self.assertGreater(calculate_training_development(allocation), 15)


class AskingChecksNothingAboutTheMentor(_MentoringWorld, HypothesisTestCase):
    @settings(max_examples=30, deadline=None)
    @given(
        key=st.sampled_from(SKILL_KEYS),
        mentor_has_tradition=flags,
        ticked=ticks,
        rating=st.integers(0, 3),
        student_in_tradition=flags,
    )
    def test_the_student_reads_the_same_whoever_she_asked(
        self,
        key: str,
        mentor_has_tradition: bool,
        ticked: set[str],
        rating: int,
        student_in_tradition: bool,
    ) -> None:
        """Maintainer (2026-11-28): "The mentor must agree".
        Implementer call: naming a mentor checks nothing about her, so the student learns
        nothing about the character she named.

        Given any mentor (with or without a Tradition, whatever it ticks, a rating from 0 to
        3) named by any student on any Magic skill: the allocation is saved with the agreement
        empty, the student reads exactly "You ask <mentor> to teach you <skill>. Your
        training waits until <mentor> agrees." and nothing else, and the mentor's character is
        sent exactly one line, "<student> asks you to teach <her> <skill>."
        """
        skill = self.skill(key)
        tradition = self.teaching_tradition(ticked, False) if mentor_has_tradition else None
        mentor = self.character(tradition, rating=rating, skill=skill)
        student = self.character(self.tradition(set()) if student_in_tradition else None)
        name = mentor.primary_persona.name

        result = ManageTrainingAction().run(
            actor=student.character,
            operation="add",
            skill_id=skill.pk,
            ap_amount=1,
            mentor_persona_id=mentor.primary_persona.pk,
        )

        self.assertTrue(result.success, result.message)
        self.assertEqual(
            result.message,
            f"You ask {name} to teach you {skill.name}. Your training waits until {name} agrees.",
        )
        row = TrainingAllocation.objects.get(character=student)
        self.assertIsNone(row.mentor_accepted_at)
        self.assertEqual(self.told(student), [])
        self.assertEqual(
            self.told(mentor),
            [
                f"{student.primary_persona.name} asks you to teach "
                f"{student.pronoun_object} {skill.name}."
            ],
        )


class WhoMayAnswerForAMentor(_MentoringWorld, HypothesisTestCase):
    @settings(max_examples=40, deadline=None)
    @given(
        key=st.sampled_from(SKILL_KEYS),
        who=st.sampled_from(
            (
                "the mentor's player",
                "the creator, when nobody plays her",
                "the creator, when someone else plays her",
                "staff",
                "the student's player",
                "staff who plays the student",
                "the borrower of a lent NPC",
                "the holder of a lent NPC",
                "a stranger",
            )
        ),
        answer=st.sampled_from(("accept", "decline", "stop")),
    )
    def test_only_the_account_that_plays_or_created_the_mentor_or_staff_may_answer(
        self, key: str, who: str, answer: str
    ) -> None:
        """Maintainer (2026-11-28): "The mentor must agree", and "The mentor is also not
        unlikely to be a GM'd NPC, so we need to accomodate that as well".

        The account that plays the mentor's character now answers for her, which is the
        borrower of a lent NPC and not its holder; when nobody plays her, the
        account that created her roster entry answers; staff always may; the account that plays
        the student never may, staff included.

        Given a request to a qualified mentor and each of those accounts (and a stranger)
        answering it by accepting, declining or stopping: the answer lands exactly for the
        accounts the rule names. For any other account it is refused with "That request is not
        addressed to a character you can answer for." and the row is unchanged. The account's
        mentoring list names the request exactly when the account may answer, so a game
        master who holds an NPC mentor reads her requests there.
        """
        creator = PlayerDataFactory()
        holder = PlayerDataFactory()
        borrower = PlayerDataFactory()
        mentor = self.mentor(key)
        if who in ("the creator, when nobody plays her", "staff"):
            RosterEntryFactory(character_sheet=mentor, created_by_account=creator.account)
        elif who == "the creator, when someone else plays her":
            entry = RosterEntryFactory(character_sheet=mentor, created_by_account=creator.account)
            RosterTenureFactory(roster_entry=entry, player_data=holder)
        elif who in ("the borrower of a lent NPC", "the holder of a lent NPC"):
            entry = RosterEntryFactory(character_sheet=mentor)
            RosterTenureFactory(roster_entry=entry, player_data=holder)
            NPCLoanFactory(
                roster_entry=entry, borrower=borrower.account, status=NPCLoanStatus.ACTIVE
            )
        else:
            self.played(mentor, holder)
        student_player = PlayerDataFactory()
        student, allocation = self.asked(key, mentor)
        self.played(student, student_player)
        if answer == "stop":
            allocation.mentor_accepted_at = timezone.now()
            allocation.save()
        accounts = {
            "the mentor's player": holder.account,
            "the creator, when nobody plays her": creator.account,
            "the creator, when someone else plays her": creator.account,
            "staff": self.staff_account(),
            "the student's player": student_player.account,
            "staff who plays the student": student_player.account,
            "the borrower of a lent NPC": borrower.account,
            "the holder of a lent NPC": holder.account,
            "a stranger": PlayerDataFactory().account,
        }
        account = accounts[who]
        if who == "staff who plays the student":
            account.is_staff = True
            account.save()
        allowed = who in (
            "the mentor's player",
            "the creator, when nobody plays her",
            "staff",
            "the borrower of a lent NPC",
        )
        service = {
            "accept": accept_mentoring,
            "decline": decline_mentoring,
            "stop": stop_mentoring,
        }[answer]
        before = mentoring_for_account(account)
        listed = [row.allocation_id for row in (*before.requests, *before.students)]

        self.assertEqual(allocation.pk in listed, allowed)
        if allowed:
            service(allocation, account)
            self.assertEqual(allocation.mentor_accepted_at is not None, answer == "accept")
            self.assertEqual(allocation.mentor_id is None, answer != "accept")
        else:
            with self.assertRaises(MentoringError) as caught:
                service(allocation, account)
            self.assertEqual(
                caught.exception.user_message,
                "That request is not addressed to a character you can answer for.",
            )
            self.assertIsNotNone(allocation.mentor_id)
            self.assertEqual(allocation.mentor_accepted_at is not None, answer == "stop")


class ChangingTheMentorAsksAgain(_MentoringWorld, HypothesisTestCase):
    # The whole domain: the three changes. The skill changes only the sentences' text.
    @settings(max_examples=3, deadline=None)
    @given(change=st.sampled_from(("ap", "same", "other")))
    def test_a_new_mentor_asks_again_and_the_same_mentor_keeps_the_agreement(
        self, change: str
    ) -> None:
        """Maintainer (2026-11-28): "The mentor must agree".
        Implementer call: changing the mentor asks again; changing only the action points
        keeps the agreement.

        Given a student whose mentor agreed, and then an update that changes only the action
        points, names the same mentor again, or names another mentor: the agreement and the
        mentor stay for the first two and no message is sent. For another mentor the
        agreement is cleared, the new mentor is sent the one request line, and the first
        mentor is told the student no longer trains with her.
        """
        key = "villainy"
        skill = self.skill(key)
        first_player, second_player = PlayerDataFactory(), PlayerDataFactory()
        first = self.mentor(key, first_player)
        second = self.mentor(key, second_player)
        student, allocation = self.asked(key, first)
        accept_mentoring(allocation, first_player.account)
        first_told = len(self.told(first))
        agreed_at = allocation.mentor_accepted_at

        if change == "ap":
            update_training_allocation(allocation, ap_amount=2)
        elif change == "same":
            update_training_allocation(allocation, mentor=first.primary_persona)
        else:
            update_training_allocation(allocation, mentor=second.primary_persona)

        if change == "other":
            self.assertIsNone(allocation.mentor_accepted_at)
            self.assertEqual(allocation.mentor_id, second.primary_persona.pk)
            self.assertEqual(
                self.told(second),
                [
                    f"{student.primary_persona.name} asks you to teach "
                    f"{student.pronoun_object} {skill.name}."
                ],
            )
            self.assertEqual(
                self.told(first)[first_told:],
                [f"{student.primary_persona.name} no longer trains {skill.name} with you."],
            )
        else:
            self.assertEqual(allocation.mentor_accepted_at, agreed_at)
            self.assertEqual(allocation.mentor_id, first.primary_persona.pk)
            self.assertEqual(self.told(second), [])
            self.assertEqual(len(self.told(first)), first_told)


class DecliningAndStoppingClearTheMentor(_MentoringWorld, HypothesisTestCase):
    # The whole domain: declining a waiting request, or stopping after agreeing. The skill
    # changes only the sentences' text.
    @settings(max_examples=2, deadline=None)
    @given(agreed_first=flags)
    def test_declining_or_stopping_clears_the_mentor_and_tells_the_student(
        self, agreed_first: bool
    ) -> None:
        """Maintainer (2026-11-28): "The mentor must agree".
        Implementer call: declining a request, or stopping teaching a student, clears the
        mentor and the agreement and tells the student; the student keeps her allocation.

        Given a request, answered by declining before the mentor agreed or by stopping after:
        the allocation row stays with its action points and no mentor, and the student reads
        "<mentor> declined to teach you <skill>." or "<mentor> stopped teaching you <skill>."
        A mentor cannot decline what she already agreed to, and cannot stop teaching a student
        she has not agreed to teach; each is refused and changes nothing.
        """
        key = "villainy"
        skill = self.skill(key)
        player = PlayerDataFactory()
        mentor = self.mentor(key, player)
        student, allocation = self.asked(key, mentor)
        name = mentor.primary_persona.name
        student_name = student.primary_persona.name
        if agreed_first:
            accept_mentoring(allocation, player.account)
            stranded = [f"{name} agreed to teach you {skill.name}."]
            with self.assertRaises(MentoringError) as caught:
                decline_mentoring(allocation, player.account)
            self.assertEqual(
                caught.exception.user_message,
                f"You already agreed to teach {student_name} {skill.name}.",
            )
            stop_mentoring(allocation, player.account)
            ending = f"{name} stopped teaching you {skill.name}."
        else:
            stranded = []
            with self.assertRaises(MentoringError) as caught:
                stop_mentoring(allocation, player.account)
            self.assertEqual(
                caught.exception.user_message,
                f"You are not teaching {student_name} {skill.name}.",
            )
            decline_mentoring(allocation, player.account)
            ending = f"{name} declined to teach you {skill.name}."

        self.assertEqual(self.told(student), [*stranded, ending])
        self.assertEqual(self.stored(student), 1)
        self.assertIsNone(allocation.mentor_id)
        self.assertIsNone(allocation.mentor_accepted_at)


class TheRowSaysWhatTheWeeklyRunWillDo(_MentoringWorld, HypothesisTestCase):
    @settings(max_examples=40, deadline=None)
    @given(
        kind=st.sampled_from(("governed", "ungoverned magic", "specialization", "not magic")),
        mentor_state=st.sampled_from(("none", "herself", "waiting", "agreed")),
        lever=flags,
    )
    def test_the_row_carries_the_teacher_line_exactly_when_the_week_skips_it_for_want_of_a_mentor(
        self, kind: str, mentor_state: str, lever: bool
    ) -> None:
        """Maintainer (2026-11-28): "The mentor must agree". Implementer call: the training row
        must not promise training the weekly run will skip.

        Given a standing allocation of 3 AP on a Magic skill a Tradition governs, a Magic skill no
        list governs, a specialization of one, or a skill outside the Magic category, with no
        mentor, her own persona, a mentor who has not agreed, or a mentor who agreed, and a student
        with or without the self-teaching lever: the row's `mentor_needed_line` is set exactly when
        the weekly run then skips the allocation for want of a mentor (spends no action points and
        sends the teacher line), and its text is the literal "<Skill> needs a teacher. Choose a
        mentor whose Tradition teaches it." naming the skill (a specialization's parent). A mentor
        who is waiting or agreed, and a skill outside the Magic category, never carry it.
        """
        if kind == "governed":
            skill = self.skills["villainy"]
        elif kind == "ungoverned magic":
            skill = self.ordinary[0]
        elif kind == "specialization":
            skill = SpecializationFactory(parent_skill=self.ordinary[1])
        else:
            skill = self.mundane
        parent = skill.parent_skill if kind == "specialization" else skill
        student = self.character()
        RosterEntryFactory(character_sheet=student)
        CharacterClassLevelFactory(character=student, level=1)
        CharacterTraitValue.objects.create(character=student, trait=parent, value=10)
        if lever:
            grant_lever(student, SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME, 1)
        if mentor_state == "herself":
            mentor = student
        elif mentor_state in ("waiting", "agreed"):
            mentor = self.character(
                self.teaching_tradition(set(TICKABLE), True), rating=2, skill=parent
            )
        else:
            mentor = None
        allocation = self.standing(student, skill, mentor, agreed=mentor_state == "agreed")
        pool = ActionPointPool.get_or_create_for_character(student.character)
        pool.current = 100
        pool.save()
        teacher_line = f"{parent.name} needs a teacher. Choose a mentor whose Tradition teaches it."
        needed = kind != "not magic" and mentor_state in ("none", "herself") and not lever

        shown = TrainingAllocationSerializer(
            allocation,
            context={"teaching_context": training_teaching_context([allocation])},
        ).data["mentor_needed_line"]
        process_weekly_training()

        pool.refresh_from_db()
        skipped_for_want_of_a_mentor = pool.current == 100 and any(
            line.endswith(teacher_line) for line in self.told(student)
        )
        self.assertEqual(shown, teacher_line if needed else None)
        self.assertEqual(skipped_for_want_of_a_mentor, needed)
