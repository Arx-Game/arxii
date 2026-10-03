"""comprehension_value: trained fluency plus active-condition fluency bonuses (#4090)."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from actions.definitions.language import TrainLanguageAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.mechanics.factories import (
    CharacterModifierFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
)
from world.mechanics.models import ModifierTarget
from world.progression.models.rewards import DevelopmentPoints
from world.species.factories import LanguageFactory
from world.species.language_services import (
    comprehension_value,
    condition_language_bonuses,
    fluency_value,
)
from world.species.models import Language, LanguageTrainingConfig
from world.traits.factories import CharacterTraitValueFactory, TraitFactory
from world.traits.models import CharacterTraitValue, TraitType


def make_language_with_target(name: str, *, restricted: bool = False):
    """A Language, its LANGUAGE trait, and the ModifierTarget pointing at that trait."""
    trait = TraitFactory(name=name, trait_type=TraitType.LANGUAGE)
    language = LanguageFactory(name=name, trait=trait, restricted=restricted)
    target = ModifierTargetFactory(
        name=name, category=ModifierCategoryFactory(name="language"), target_trait=trait
    )
    return language, target


def make_understanding_condition(name: str, target, *, value: int = 20):
    template = ConditionTemplateFactory(name=name)
    ConditionModifierEffectFactory(
        condition=template, modifier_target=target, value=value, scales_with_severity=True
    )
    return template


def _train(sheet, language, value: int) -> None:
    CharacterTraitValueFactory(character=sheet, trait=language.trait, value=value)


class ComprehensionValueTests(TestCase):
    def setUp(self) -> None:
        ModifierTarget.clear_trait_cache()
        CharacterTraitValue.flush_instance_cache()
        self.language, self.target = make_language_with_target("CompTestTongueA")
        self.other_language, self.other_target = make_language_with_target("CompTestTongueB")
        self.condition = make_understanding_condition("Placeholder Understanding", self.target)
        self.sheet = CharacterSheetFactory()

    def test_no_condition_equals_trained(self) -> None:
        _train(self.sheet, self.language, 20)
        self.assertEqual(comprehension_value(self.sheet, self.language), 20)

    def test_condition_adds_to_trained_and_scales_with_severity(self) -> None:
        _train(self.sheet, self.language, 20)
        ConditionInstanceFactory(target=self.sheet.character, condition=self.condition, severity=2)
        self.assertEqual(comprehension_value(self.sheet, self.language), 60)
        self.assertEqual(fluency_value(self.sheet, self.language), 20)

    def test_row_for_language_a_does_nothing_for_language_b(self) -> None:
        ConditionInstanceFactory(target=self.sheet.character, condition=self.condition, severity=4)
        self.assertEqual(comprehension_value(self.sheet, self.other_language), 0)

    def test_distinction_modifier_toward_the_target_is_ignored(self) -> None:
        CharacterModifierFactory(character=self.sheet, target=self.target, value=60)
        self.assertEqual(comprehension_value(self.sheet, self.language), 0)

    def test_negative_bonus_floors_at_zero(self) -> None:
        _train(self.sheet, self.language, 20)
        curse = ConditionTemplateFactory(name="Placeholder Muddled Ears")
        ConditionModifierEffectFactory(condition=curse, modifier_target=self.target, value=-50)
        ConditionInstanceFactory(target=self.sheet.character, condition=curse)
        self.assertEqual(comprehension_value(self.sheet, self.language), 0)

    def test_no_trait_or_no_target_gives_trained_value(self) -> None:
        traitless = Language.objects.create(name="CompTestTraitless")
        self.assertEqual(comprehension_value(self.sheet, traitless), 0)
        bare_trait = TraitFactory(name="CompTestNoTarget", trait_type=TraitType.LANGUAGE)
        untargeted = LanguageFactory(name="CompTestNoTarget", trait=bare_trait)
        CharacterTraitValueFactory(character=self.sheet, trait=bare_trait, value=35)
        self.assertEqual(comprehension_value(self.sheet, untargeted), 35)

    def test_bonuses_name_their_source_conditions(self) -> None:
        ConditionInstanceFactory(target=self.sheet.character, condition=self.condition, severity=2)
        bonuses = condition_language_bonuses(self.sheet)
        self.assertEqual(set(bonuses), {self.language.pk})
        self.assertEqual(bonuses[self.language.pk].total, 40)
        self.assertEqual(bonuses[self.language.pk].sources, ("Placeholder Understanding",))

    def test_expired_ingame_condition_counts_for_nothing_and_is_not_torn_down(self) -> None:
        """F2: the read skips a lapsed in-game-time condition and never deletes it."""
        _train(self.sheet, self.language, 20)
        lapsed = ConditionTemplateFactory(
            name="Placeholder Lapsed Understanding",
            default_duration_type=DurationType.INGAME_TIME,
        )
        ConditionModifierEffectFactory(condition=lapsed, modifier_target=self.target, value=60)
        instance = ConditionInstanceFactory(
            target=self.sheet.character,
            condition=lapsed,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.assertEqual(comprehension_value(self.sheet, self.language), 20)
        self.assertEqual(condition_language_bonuses(self.sheet), {})
        self.assertTrue(ConditionInstance.objects.filter(pk=instance.pk).exists())


class CanonicalTargetTests(TestCase):
    """F3: with two targets on one language trait, only get_for_trait's pick counts."""

    def setUp(self) -> None:
        ModifierTarget.clear_trait_cache()
        self.language, first_target = make_language_with_target("CompTwoTargetTongue")
        second_target = ModifierTargetFactory(
            name="CompTwoTargetTongueAlias",
            category=ModifierCategoryFactory(name="language"),
            target_trait=self.language.trait,
        )
        self.canonical = ModifierTarget.get_for_trait(self.language.trait)
        self.ignored = second_target if self.canonical == first_target else first_target
        self.sheet = CharacterSheetFactory()
        counted = ConditionTemplateFactory(name="Placeholder Counted Understanding")
        ConditionModifierEffectFactory(condition=counted, modifier_target=self.canonical, value=40)
        ignored = ConditionTemplateFactory(name="Placeholder Ignored Understanding")
        ConditionModifierEffectFactory(condition=ignored, modifier_target=self.ignored, value=30)
        ConditionInstanceFactory(target=self.sheet.character, condition=counted)
        ConditionInstanceFactory(target=self.sheet.character, condition=ignored)

    def test_feed_and_bonuses_agree_on_the_canonical_target(self) -> None:
        self.assertNotEqual(self.canonical, self.ignored)
        self.assertEqual(comprehension_value(self.sheet, self.language), 40)
        bonus = condition_language_bonuses(self.sheet)[self.language.pk]
        self.assertEqual(bonus.total, 40)
        self.assertEqual(bonus.sources, ("Placeholder Counted Understanding",))


class ConditionDoesNotTrainOrTeachTests(TestCase):
    """F5: teaching and restricted self-study stay on trained fluency."""

    def setUp(self) -> None:
        ModifierTarget.clear_trait_cache()
        DevelopmentPoints.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        LanguageTrainingConfig.objects.flush_singleton_cache()
        self.room = ObjectDBFactory(
            db_key="CompTrainingRoom", db_typeclass_path="typeclasses.rooms.Room"
        )

    def _sheeted(self, key: str):
        character = CharacterFactory(db_key=key, location=self.room)
        return character, CharacterSheetFactory(character=character)

    def test_condition_fluent_teacher_is_not_a_fluent_teacher(self) -> None:
        language, target = make_language_with_target("CompTeachTongue")
        condition = make_understanding_condition("Placeholder Teacher Understanding", target)
        student, _student_sheet = self._sheeted("Student")
        teacher, teacher_sheet = self._sheeted("Teacher")
        ConditionInstanceFactory(target=teacher, condition=condition, severity=4)
        self.assertEqual(comprehension_value(teacher_sheet, language), 80)

        result = TrainLanguageAction().run(student, language_id=language.pk, teacher_id=teacher.pk)

        self.assertTrue(result.success, result.message)
        self.assertTrue(result.data["self_study"])

    def test_restricted_self_study_at_trained_zero_is_still_refused(self) -> None:
        language, target = make_language_with_target("CompRestrictedTongue", restricted=True)
        condition = make_understanding_condition("Placeholder Student Understanding", target)
        student, student_sheet = self._sheeted("Student")
        ConditionInstanceFactory(target=student, condition=condition, severity=4)
        self.assertEqual(comprehension_value(student_sheet, language), 80)

        result = TrainLanguageAction().run(student, language_id=language.pk)

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            f"No one can teach you {language.name}, and it is not a tongue "
            "you can puzzle out alone.",
        )
