"""CharacterDraft.magic_training_pool (slice 2 of #4659)."""

from django.test import TestCase

from world.character_creation.constants import (
    CG_MODIFIER_CATEGORY,
    MAGIC_TRAINING_POINTS_TARGET,
)
from world.character_creation.factories import CharacterDraftFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.magic.factories import (
    AffinityFactory,
    GiftFactory,
    ResonanceFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.types.aura import AffinityType
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.skills.factories import SkillFactory, SkillPointBudgetFactory
from world.traits.factories import SkillTraitFactory
from world.traits.models import TraitCategory


class MagicTrainingPoolTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        category = ModifierCategoryFactory(name=CG_MODIFIER_CATEGORY)
        cls.target = ModifierTargetFactory(name=MAGIC_TRAINING_POINTS_TARGET, category=category)
        SkillPointBudgetFactory(pk=1)
        cls.gift = GiftFactory()
        cls.affinity = AffinityFactory(aura_type=AffinityType.CELESTIAL)
        cls.resonance = ResonanceFactory(affinity=cls.affinity)
        cls.tradition = TraditionFactory()
        cls.tradition.favored_affinities.add(cls.affinity)
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        cls.training = DistinctionFactory(name="Tradition Training")
        DistinctionEffectFactory(distinction=cls.training, target=cls.target, value_per_rank=20)
        cls.studious = DistinctionFactory(name="Studious")
        DistinctionEffectFactory(distinction=cls.studious, target=cls.target, value_per_rank=10)

    def _draft(self, distinctions, *, gift=True, affinity=True, tradition=True):
        data = {"distinctions": [{"distinction_id": d.id, "rank": 1} for d in distinctions]}
        if gift:
            data["selected_gift_id"] = self.gift.id
        else:
            data["selected_gift_id"] = GiftFactory().id
        if affinity:
            data["selected_gift_resonance_id"] = self.resonance.id
        else:
            data["selected_gift_resonance_id"] = ResonanceFactory(
                affinity=AffinityFactory(aura_type=AffinityType.ABYSSAL)
            ).id
        return CharacterDraftFactory(
            draft_data=data, selected_tradition=self.tradition if tradition else None
        )

    def test_both_fits(self) -> None:
        pool = self._draft([self.training, self.studious]).magic_training_pool
        self.assertEqual((pool.base, pool.gift_bonus, pool.affinity_bonus), (30, 10, 10))
        self.assertEqual(pool.total, 50)
        self.assertEqual(pool.sources, [("Studious", 10), ("Tradition Training", 20)])

    def test_gift_only(self) -> None:
        pool = self._draft([self.training, self.studious], affinity=False).magic_training_pool
        self.assertEqual(pool.total, 40)

    def test_neither(self) -> None:
        pool = self._draft(
            [self.training, self.studious], gift=False, affinity=False
        ).magic_training_pool
        self.assertEqual(pool.total, 30)

    def test_no_training_gives_nothing(self) -> None:
        pool = self._draft([]).magic_training_pool
        self.assertEqual((pool.base, pool.total, pool.required_spend), (0, 0, 0))
        self.assertEqual(pool.sources, [])

    def test_total_rounds_down_to_tier(self) -> None:
        review = DistinctionFactory(name="Review Focus")
        DistinctionEffectFactory(distinction=review, target=self.target, value_per_rank=25)
        pool = self._draft([review], gift=False, affinity=False).magic_training_pool
        self.assertEqual(pool.total, 20)

    def test_required_spend_capped_by_magic_skills(self) -> None:
        for _ in range(3):
            SkillFactory(trait=SkillTraitFactory(category=TraitCategory.MAGIC))
        big = DistinctionFactory(name="Big")
        DistinctionEffectFactory(distinction=big, target=self.target, value_per_rank=200)
        pool = self._draft([big], gift=False, affinity=False).magic_training_pool
        self.assertEqual((pool.total, pool.required_spend), (200, 90))


class MagicSkillAllocationTest(TestCase):
    """The Gift stage's Magic skill allocation (task 4 of slice 2 of #4659)."""

    @classmethod
    def setUpTestData(cls) -> None:
        category = ModifierCategoryFactory(name=CG_MODIFIER_CATEGORY)
        cls.target = ModifierTargetFactory(name=MAGIC_TRAINING_POINTS_TARGET, category=category)
        SkillPointBudgetFactory(pk=1)
        cls.gift = GiftFactory()
        cls.other_gift = GiftFactory()
        cls.tradition = TraditionFactory()
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        training = DistinctionFactory(name="Tradition Training")
        DistinctionEffectFactory(distinction=training, target=cls.target, value_per_rank=30)
        cls.training = training
        cls.skills = [
            SkillFactory(trait=SkillTraitFactory(category=TraitCategory.MAGIC)) for _ in range(3)
        ]
        cls.combat = SkillFactory(trait=SkillTraitFactory(category=TraitCategory.COMBAT))
        cls.resonance = ResonanceFactory(affinity=AffinityFactory(aura_type=AffinityType.ABYSSAL))

    def _draft(self, magic_skills, *, gift=None, trained=True):
        data = {
            "selected_gift_id": (gift or self.gift).id,
            "selected_gift_resonance_id": self.resonance.id,
            "distinctions": ([{"distinction_id": self.training.id, "rank": 1}] if trained else []),
            "magic_skills": magic_skills,
        }
        return CharacterDraftFactory(draft_data=data, selected_tradition=self.tradition)

    def _errors(self, magic_skills, **kwargs):
        from world.character_creation.validators import _magic_skill_allocation_errors

        return _magic_skill_allocation_errors(self._draft(magic_skills, **kwargs))

    def test_exact_spend_passes(self) -> None:
        # Pool 30 (Gift fits: +10 -> 40).
        alloc = {str(self.skills[0].pk): 30, str(self.skills[1].pk): 10}
        self.assertEqual(self._errors(alloc), [])

    def test_under_spend_fails(self) -> None:
        alloc = {str(self.skills[0].pk): 30}
        self.assertEqual(self._errors(alloc), ["Spend all of your magical training: 10 left"])

    def test_over_after_swapping_gift(self) -> None:
        alloc = {str(self.skills[0].pk): 30, str(self.skills[1].pk): 10}
        self.assertEqual(self._errors(alloc), [])
        self.assertEqual(
            self._errors(alloc, gift=self.other_gift), ["Your magical training is over by 10"]
        )

    def test_non_magic_skill_fails(self) -> None:
        alloc = {str(self.combat.pk): 30, str(self.skills[0].pk): 10}
        self.assertEqual(self._errors(alloc), ["Magic skills only"])

    def test_inactive_magic_skill_fails(self) -> None:
        lapsed = SkillFactory(
            trait=SkillTraitFactory(category=TraitCategory.MAGIC), is_active=False
        )
        self.assertEqual(self._errors({str(lapsed.pk): 40}), ["Magic skills only"])

    def test_off_step_value_fails(self) -> None:
        alloc = {str(self.skills[0].pk): 15, str(self.skills[1].pk): 25}
        self.assertEqual(self._errors(alloc), ["Magic skill values go in steps of 10 up to 30"])

    def test_no_pool_and_empty_allocation_passes(self) -> None:
        self.assertEqual(self._errors({}, trained=False), [])

    def test_no_pool_with_allocation_fails(self) -> None:
        self.assertEqual(
            self._errors({str(self.skills[0].pk): 10}, trained=False),
            ["Your magical training is over by 10"],
        )
