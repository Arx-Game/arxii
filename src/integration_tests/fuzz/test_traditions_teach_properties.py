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
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

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
from world.covenants.factories import CombatStyleFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.magic.constants import AFFINITY_ABYSSAL, AFFINITY_CELESTIAL, AFFINITY_PRIMAL
from world.magic.factories import (
    CharacterTraditionFactory,
    TraditionFactory,
    ensure_conversion_pairs,
)
from world.magic.models import Affinity, Tradition
from world.magic.services.tradition_teaching import (
    build_teaching_context,
    is_outsider,
    is_tradition_governed,
    taught_affinity_skill_names_by_tradition,
    tradition_teaches,
)
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.skills.factories import MagicSkillFactory, SkillPointBudgetFactory
from world.skills.models import Skill

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
