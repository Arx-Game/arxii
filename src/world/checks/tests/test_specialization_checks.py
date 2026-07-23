"""Specializations participate in checks — the stat + skill + specialization shape (#1688).

The parent skill rides the ordinary CheckTypeTrait path (a skill is Trait-backed); this covers
the new third leg: a CheckTypeSpecialization (or a runtime-chosen specialization) folds the
character's owned specialization value into the roll, and contributes nothing when unowned.
"""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import (
    CheckCategoryFactory,
    CheckTypeFactory,
    CheckTypeSpecializationFactory,
    CheckTypeTraitFactory,
)
from world.checks.services import _calculate_specialization_points, perform_check
from world.skills.factories import (
    CharacterSpecializationValueFactory,
    SkillFactory,
    SpecializationFactory,
)
from world.skills.services import get_specialization_value, has_specialization
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitCategory,
    TraitType,
)


class SpecializationInCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        CheckSystemSetupFactory.create()
        # Stats and skills (specs convert like skills) both need a conversion range.
        for trait_type in (TraitType.STAT, TraitType.SKILL):
            PointConversionRange.objects.get_or_create(
                trait_type=trait_type,
                min_value=1,
                defaults={"max_value": 100, "points_per_level": 1},
            )
        for rank_val, min_pts, name in [(0, 0, "S0"), (1, 10, "S1"), (2, 25, "S2"), (3, 50, "S3")]:
            CheckRank.objects.get_or_create(
                rank=rank_val, defaults={"min_points": min_pts, "name": name}
            )
        cls.character = CharacterSheetFactory().character
        cls.charm, _ = Trait.objects.get_or_create(
            name="spec_test_charm",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.SOCIAL},
        )
        cls.persuasion_trait, _ = Trait.objects.get_or_create(
            name="spec_test_persuasion",
            defaults={"trait_type": TraitType.SKILL, "category": TraitCategory.SOCIAL},
        )
        cls.persuasion = SkillFactory(trait=cls.persuasion_trait)
        cls.seduction = SpecializationFactory(
            parent_skill=cls.persuasion, name="spec_test_seduction"
        )
        cls.category = CheckCategoryFactory(name="spec_test_social")
        # Seduce check: charm (stat) + Persuasion (skill, via CheckTypeTrait on its trait)
        # + Seduction (specialization).
        cls.check_type = CheckTypeFactory(name="spec_test_seduce", category=cls.category)
        CheckTypeTraitFactory(check_type=cls.check_type, trait=cls.charm, weight=Decimal("1.0"))
        CheckTypeTraitFactory(
            check_type=cls.check_type, trait=cls.persuasion_trait, weight=Decimal("1.0")
        )
        CheckTypeSpecializationFactory(
            check_type=cls.check_type, specialization=cls.seduction, weight=Decimal("1.0")
        )

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()

    def test_unowned_specialization_contributes_zero(self):
        # A non-specialist simply rolls stat + skill — the spec adds nothing.
        assert _calculate_specialization_points(self.character, self.check_type) == 0

    def test_owned_specialization_adds_points(self):
        CharacterSpecializationValueFactory(
            character=self.character.sheet_data, specialization=self.seduction, value=30
        )
        assert _calculate_specialization_points(self.character, self.check_type) > 0

    def test_specialization_raises_total_points_through_perform_check(self):
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=self.charm, value=30
        )
        base = perform_check(self.character, self.check_type, target_difficulty=0)
        assert base.specialization_points == 0
        CharacterSpecializationValueFactory(
            character=self.character.sheet_data, specialization=self.seduction, value=30
        )
        with_spec = perform_check(self.character, self.check_type, target_difficulty=0)
        assert with_spec.specialization_points > 0
        assert with_spec.total_points > base.total_points

    def test_runtime_specialization_adds_points(self):
        # A check with no fixed spec; the spec is chosen at call time (e.g. which Performance art).
        bare = CheckTypeFactory(name="spec_test_bare", category=self.category)
        CheckTypeTraitFactory(check_type=bare, trait=self.charm, weight=Decimal("1.0"))
        CharacterSpecializationValueFactory(
            character=self.character.sheet_data, specialization=self.seduction, value=30
        )
        assert _calculate_specialization_points(self.character, bare) == 0
        assert (
            _calculate_specialization_points(
                self.character, bare, runtime_specialization=self.seduction
            )
            > 0
        )

    def test_has_specialization_gate(self):
        assert has_specialization(self.character, self.seduction) is False
        CharacterSpecializationValueFactory(
            character=self.character.sheet_data, specialization=self.seduction, value=10
        )
        assert has_specialization(self.character, self.seduction) is True  # rank 1 = value 10
        assert has_specialization(self.character, self.seduction, minimum_rank=2) is False

    def test_get_specialization_value(self):
        assert get_specialization_value(self.character, self.seduction) == 0
        CharacterSpecializationValueFactory(
            character=self.character.sheet_data, specialization=self.seduction, value=20
        )
        assert get_specialization_value(self.character, self.seduction) == 20
