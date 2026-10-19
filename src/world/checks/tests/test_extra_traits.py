"""``extra_traits``: skill terms a caller adds to one roll at call time (#4450).

The engine treats each ``ExtraTraitTerm`` like an extra ``CheckTypeTrait`` row: its weighted
value converts to points, its trait earns check-based development, and its trait id rides
the capability ``involved_traits``. ``()`` (the default) leaves every roll unchanged.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import (
    CheckCategoryFactory,
    CheckTypeCapabilityModifierFactory,
    CheckTypeFactory,
    CheckTypeTraitFactory,
)
from world.checks.services import (
    collect_check_modifiers,
    compute_check_rating,
    perform_check,
    preview_check_difficulty,
)
from world.checks.test_helpers import force_check_outcome
from world.checks.types import ExtraTraitTerm
from world.conditions.factories import CapabilityTypeFactory
from world.conditions.services import get_effective_capability_value
from world.fatigue.constants import EffortLevel
from world.progression.models import WeeklySkillUsage
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitCategory,
    TraitType,
)

SKILL_VALUE = 30


class ExtraTraitTermTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        CheckSystemSetupFactory.create()
        for trait_type in (TraitType.STAT, TraitType.SKILL):
            PointConversionRange.objects.get_or_create(
                trait_type=trait_type,
                min_value=1,
                defaults={"max_value": 100, "points_per_level": 1},
            )
        for rank_val, min_pts, name in [
            (0, 0, "ET0"),
            (1, 10, "ET1"),
            (2, 25, "ET2"),
            (3, 50, "ET3"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val, defaults={"min_points": min_pts, "name": name}
            )
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.stat, _ = Trait.objects.get_or_create(
            name="extra_traits_stat",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.MENTAL},
        )
        cls.skill, _ = Trait.objects.get_or_create(
            name="extra_traits_skill",
            defaults={"trait_type": TraitType.SKILL, "category": TraitCategory.COMBAT},
        )
        cls.other_skill, _ = Trait.objects.get_or_create(
            name="extra_traits_other_skill",
            defaults={"trait_type": TraitType.SKILL, "category": TraitCategory.COMBAT},
        )
        cls.check_type = CheckTypeFactory(
            name="extra_traits_check",
            category=CheckCategoryFactory(name="extra_traits_category"),
        )
        CheckTypeTraitFactory(check_type=cls.check_type, trait=cls.stat, weight=Decimal("1.0"))
        for trait, value in ((cls.stat, 20), (cls.skill, SKILL_VALUE), (cls.other_skill, 40)):
            CharacterTraitValue.objects.create(
                character=cls.character.sheet_data, trait=trait, value=value
            )

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()

    def _term(self, trait, weight="1.00"):
        return ExtraTraitTerm(trait=trait, weight=Decimal(weight))

    def test_term_adds_converted_points(self):
        base = perform_check(self.character, self.check_type)
        with_term = perform_check(
            self.character, self.check_type, extra_traits=[self._term(self.skill)]
        )
        self.assertEqual(with_term.trait_points, base.trait_points + SKILL_VALUE)

    def test_weight_scales_term(self):
        base = perform_check(self.character, self.check_type)
        with_term = perform_check(
            self.character, self.check_type, extra_traits=[self._term(self.skill, "0.50")]
        )
        self.assertEqual(with_term.trait_points, base.trait_points + SKILL_VALUE // 2)

    def test_empty_default_unchanged(self):
        omitted = perform_check(self.character, self.check_type)
        explicit = perform_check(self.character, self.check_type, extra_traits=())
        self.assertEqual(omitted.total_points, explicit.total_points)
        self.assertEqual(omitted.trait_points, explicit.trait_points)

    def test_duplicate_trait_counts_points_twice_develops_once(self):
        check_type = CheckTypeFactory(
            name="extra_traits_dup_check",
            category=CheckCategoryFactory(name="extra_traits_dup_category"),
        )
        CheckTypeTraitFactory(check_type=check_type, trait=self.skill, weight=Decimal("1.0"))
        once = perform_check(self.character, check_type)
        twice = perform_check(
            self.character,
            check_type,
            effort_level=EffortLevel.MEDIUM,
            extra_traits=[self._term(self.skill)],
        )
        self.assertEqual(twice.trait_points, once.trait_points + SKILL_VALUE)
        usage = WeeklySkillUsage.objects.filter(character_sheet=self.sheet, trait=self.skill)
        self.assertEqual(usage.count(), 1)
        self.assertEqual(usage.get().check_count, 1)

    def test_term_trait_gets_development(self):
        perform_check(
            self.character,
            self.check_type,
            effort_level=EffortLevel.MEDIUM,
            extra_traits=[self._term(self.other_skill)],
        )
        usage = WeeklySkillUsage.objects.get(character_sheet=self.sheet, trait=self.other_skill)
        self.assertEqual(usage.check_count, 1)

    def test_term_trait_gets_no_development_without_effort(self):
        perform_check(self.character, self.check_type, extra_traits=[self._term(self.other_skill)])
        self.assertFalse(WeeklySkillUsage.objects.filter(trait=self.other_skill).exists())

    def test_forced_outcome_path_scores_and_develops_term(self):
        outcome = CheckOutcomeFactory(name="extra_traits_forced", success_level=1)
        base = perform_check(self.character, self.check_type)
        with force_check_outcome(outcome) as capture:
            result = perform_check(
                self.character,
                self.check_type,
                effort_level=EffortLevel.MEDIUM,
                extra_traits=[self._term(self.skill)],
            )
        self.assertEqual(result.trait_points, base.trait_points + SKILL_VALUE)
        self.assertEqual(capture.extra_traits, (self._term(self.skill),))
        self.assertTrue(WeeklySkillUsage.objects.filter(trait=self.skill).exists())

    def test_compute_check_rating_and_preview_include_term(self):
        term = [self._term(self.skill)]
        base_rating = compute_check_rating(self.character, self.check_type)
        self.assertEqual(
            compute_check_rating(self.character, self.check_type, extra_traits=term),
            base_rating + SKILL_VALUE,
        )
        # Stat 20 + level 5 = 25 (rank 2); the term lifts it to 55 (rank 3).
        base_preview = preview_check_difficulty(self.character, self.check_type, 25)
        with_term = preview_check_difficulty(self.character, self.check_type, 25, extra_traits=term)
        self.assertEqual(with_term, base_preview + 1)

    def test_involved_traits_include_term(self):
        capability = CapabilityTypeFactory(name="extra_traits_capability")
        check_type = CheckTypeFactory(
            name="extra_traits_cap_check",
            category=CheckCategoryFactory(name="extra_traits_cap_category"),
        )
        CheckTypeTraitFactory(check_type=check_type, trait=self.stat, weight=Decimal("1.0"))
        CheckTypeCapabilityModifierFactory(check_type=check_type, capability=capability)
        term = self._term(self.skill)

        with patch(
            "world.conditions.services.get_effective_capability_value",
            wraps=get_effective_capability_value,
        ) as oracle:
            perform_check(self.character, check_type, extra_traits=[term])
            roll_ctx = oracle.call_args.kwargs["action_ctx"]
            oracle.reset_mock()
            collect_check_modifiers(self.sheet, check_type, extra_traits=[term])
            provenance_ctx = oracle.call_args.kwargs["action_ctx"]
            oracle.reset_mock()
            perform_check(self.character, check_type)
            plain_ctx = oracle.call_args.kwargs["action_ctx"]

        self.assertEqual(set(roll_ctx.involved_traits), {self.stat.pk, self.skill.pk})
        self.assertEqual(set(provenance_ctx.involved_traits), {self.stat.pk, self.skill.pk})
        self.assertEqual(plain_ctx.involved_traits, (self.stat.pk,))
