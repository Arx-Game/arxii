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
