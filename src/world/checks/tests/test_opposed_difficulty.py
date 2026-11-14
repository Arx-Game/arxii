"""Tests for the two mutually-exclusive answers to what the opposing side of a
check contributes (#2707, Task 4):

* ``level_opposition`` -- the PASSIVE half: a defender's level plus (when a
  character is given) the acting check's aspects scored against the
  defender's Path.
* ``compute_resist_increment`` -- the ACTIVE half: a defender's full pre-roll
  rating on their own defence check (Composure), now routed through
  ``compute_check_rating`` instead of trait points alone (gap 1).

The two are deliberately exclusive -- an active rating already contains the
defender's level points, so a call site never uses both.
"""

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import LEVEL_POINTS_PER_LEVEL
from world.checks.factories import (
    CheckTypeAspectFactory,
    CheckTypeCapabilityModifierFactory,
    CheckTypeFactory,
    CheckTypeSpecializationFactory,
    create_resistance_check_types,
)
from world.checks.services import compute_check_rating, compute_resist_increment, level_opposition
from world.classes.factories import (
    AspectFactory,
    CharacterClassFactory,
    CharacterClassLevelFactory,
    PathAspectFactory,
    PathFactory,
)
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.fatigue.constants import EFFORT_CHECK_MODIFIER
from world.progression.factories import CharacterPathHistoryFactory
from world.skills.factories import CharacterSpecializationValueFactory, SpecializationFactory
from world.traits.factories import StatTraitFactory
from world.traits.models import CharacterTraitValue, PointConversionRange, Trait, TraitType


class OpposedDifficultyTests(TestCase):
    """level_opposition (passive) and compute_resist_increment (active) -- #2707."""

    @classmethod
    def setUpTestData(cls):
        Trait.flush_instance_cache()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )

        # --- level_opposition fixtures: a check whose aspect matches the
        # voice_adept's Path, so their wheelhouse raises the passive term. ---
        cls.check_type = CheckTypeFactory(name="OpposedTestCheck")
        cls.voice_path = PathFactory(name="OpposedTestVoicePath")
        cls.voice_aspect = AspectFactory(name="OpposedTestVoiceAspect")
        PathAspectFactory(character_path=cls.voice_path, aspect=cls.voice_aspect, weight=2)
        CheckTypeAspectFactory(
            check_type=cls.check_type, aspect=cls.voice_aspect, weight=Decimal("1.0")
        )
        cls.voice_adept = CharacterSheetFactory().character
        CharacterPathHistoryFactory(character=cls.voice_adept.sheet_data, path=cls.voice_path)

        # --- compute_resist_increment fixtures ---
        check_types = create_resistance_check_types()
        cls.composure_check_type = check_types["Composure"]
        cls.willpower_trait = StatTraitFactory(name="willpower")

        cls.plain_defender = CharacterSheetFactory().character
        CharacterTraitValue.objects.create(
            character=cls.plain_defender.sheet_data, trait=cls.willpower_trait, value=10
        )

        # decorated_defender owns the same willpower value PLUS a Path/aspect
        # match, an owned specialization, and an authored capability -- the
        # terms gap 1 was dropping.
        cls.decorated_defender = CharacterSheetFactory().character
        CharacterTraitValue.objects.create(
            character=cls.decorated_defender.sheet_data, trait=cls.willpower_trait, value=10
        )

        decorated_path = PathFactory(name="OpposedTestDecoratedPath")
        decorated_aspect = AspectFactory(name="OpposedTestDecoratedAspect")
        PathAspectFactory(character_path=decorated_path, aspect=decorated_aspect, weight=2)
        CheckTypeAspectFactory(
            check_type=cls.composure_check_type,
            aspect=decorated_aspect,
            weight=Decimal("1.0"),
        )
        CharacterPathHistoryFactory(
            character=cls.decorated_defender.sheet_data, path=decorated_path
        )

        specialization = SpecializationFactory(name="OpposedTestComposureSpec")
        CheckTypeSpecializationFactory(
            check_type=cls.composure_check_type,
            specialization=specialization,
            weight=Decimal("1.0"),
        )
        CharacterSpecializationValueFactory(
            character=cls.decorated_defender.sheet_data,
            specialization=specialization,
            value=10,
        )

        capability = CapabilityTypeFactory(name="OpposedTestCapability", innate_baseline=3)
        CheckTypeCapabilityModifierFactory(
            check_type=cls.composure_check_type,
            capability=capability,
            weight=Decimal("1.0"),
        )

        # --- level_override fixtures (#2707 whole-branch-review finding 4) ---
        # Two defenders sharing traits, path, and aspect match -- the ONLY difference
        # is their real authored level (3 vs 10) -- so level_override=10 on the level-3
        # defender can be pinned against the level-10 defender's ACTUAL rating: if the
        # override merely substituted, the two must match exactly; if it instead added
        # on top of the level-3 defender's own level, they would not.
        override_class = CharacterClassFactory()
        cls.override_low = CharacterSheetFactory().character
        CharacterTraitValue.objects.create(
            character=cls.override_low.sheet_data, trait=cls.willpower_trait, value=10
        )
        CharacterPathHistoryFactory(character=cls.override_low.sheet_data, path=decorated_path)
        CharacterClassLevelFactory(
            character=cls.override_low.sheet_data,
            character_class=override_class,
            level=3,
            is_primary=True,
        )

        cls.override_high = CharacterSheetFactory().character
        CharacterTraitValue.objects.create(
            character=cls.override_high.sheet_data, trait=cls.willpower_trait, value=10
        )
        CharacterPathHistoryFactory(character=cls.override_high.sheet_data, path=decorated_path)
        CharacterClassLevelFactory(
            character=cls.override_high.sheet_data,
            character_class=override_class,
            level=10,
            is_primary=True,
        )

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()

    def test_level_opposition_scales_with_level(self):
        low = level_opposition(self.check_type, level=1)
        high = level_opposition(self.check_type, level=5)
        self.assertEqual(high - low, LEVEL_POINTS_PER_LEVEL * 4)

    def test_level_opposition_adds_the_defenders_aspect_match(self):
        """Their wheelhouse protects them: the ACTING check's aspects scored against
        the DEFENDER's Path (#2707 decision 5)."""
        plain = level_opposition(self.check_type, level=5)
        matched = level_opposition(self.check_type, level=5, character=self.voice_adept)
        self.assertGreater(matched, plain)

    def test_level_opposition_without_a_character_is_level_alone(self):
        """An ephemeral NPC with no sheet contributes level and nothing else."""
        self.assertEqual(level_opposition(self.check_type, level=4), LEVEL_POINTS_PER_LEVEL * 4)

    def test_level_opposition_folds_in_the_opposed_entitys_conditions(self):
        """#3384: a penalty condition on the opposed entity LOWERS the total --
        no sign flip, summed as-authored (ADR-0166's additive opposing-side shape)."""
        opponent = ObjectDBFactory(db_key="OpposedDifficultyConditionTarget")
        staggered = ConditionTemplateFactory(name="OpposedDifficultyStaggered")
        ConditionCheckModifierFactory(
            condition=staggered,
            check_type=self.check_type,
            modifier_value=-15,
        )

        without_condition = level_opposition(self.check_type, level=5, character=opponent)

        ConditionInstanceFactory(target=opponent, condition=staggered)
        with_condition = level_opposition(self.check_type, level=5, character=opponent)

        self.assertEqual(without_condition - with_condition, 15)

    def test_level_opposition_condition_composes_additively_with_level_and_aspect(self):
        """The condition term is a THIRD additive term alongside level points and the
        aspect bonus, not a replacement for either."""
        staggered = ConditionTemplateFactory(name="OpposedDifficultyComposesStaggered")
        ConditionCheckModifierFactory(
            condition=staggered,
            check_type=self.check_type,
            modifier_value=-15,
        )

        # level points + aspect bonus, no condition yet
        with_aspect_only = level_opposition(self.check_type, level=5, character=self.voice_adept)

        ConditionInstanceFactory(target=self.voice_adept, condition=staggered)
        with_aspect_and_condition = level_opposition(
            self.check_type, level=5, character=self.voice_adept
        )

        self.assertEqual(with_aspect_and_condition, with_aspect_only - 15)

    def test_resist_increment_now_carries_aspect_specialization_and_capability(self):
        """Gap 1: the resist side was trait-points-only."""
        bare = compute_resist_increment(self.plain_defender, "medium")
        rich = compute_resist_increment(self.decorated_defender, "medium")
        self.assertGreater(rich, bare)

    def test_resist_increment_is_exactly_rating_plus_effort(self):
        """compute_resist_increment adds no LEVEL term beyond the Composure rating + effort.

        For a defender carrying no modifier on Composure rolls, which this one is; the
        modifiers a defender does carry are pinned in ResistCountsComposureModifiersTests
        (#4720).

        Pins the exact composition rather than restating the implementation: the
        active-half result must equal compute_check_rating(defender, Composure) plus
        the effort-level modifier, clamped to >= 0, with nothing else folded in. This
        is what makes compute_resist_increment and level_opposition mutually
        exclusive (#2707, ADR-0166) -- if compute_resist_increment carried an extra
        term beyond the rating, a call site combining it with level_opposition
        wouldn't obviously double-count the defender's level, since the rating
        already contains it.
        """
        active = compute_resist_increment(self.plain_defender, "medium")
        rating = compute_check_rating(self.plain_defender, self.composure_check_type)
        self.assertEqual(active, max(0, rating + EFFORT_CHECK_MODIFIER["medium"]))

    def test_level_override_none_is_byte_identical_to_omitting_it(self):
        """Whole-branch-review finding 4: level_override=None must change nothing.

        Pinned against BOTH the plain defender (no CharacterClassLevel rows, floors
        at 1) and the decorated defender (a real authored level via
        CharacterPathHistory/aspect scaling), since the override threads through both
        the level_points term and the aspect-bonus level scaling.
        """
        for defender in (self.plain_defender, self.decorated_defender):
            omitted = compute_resist_increment(defender, "medium")
            explicit_none = compute_resist_increment(defender, "medium", level_override=None)
            self.assertEqual(omitted, explicit_none)

    def test_level_override_matches_a_real_character_actually_being_that_level(self):
        """The override reproduces exactly what a real level-10 defender rates.

        override_low and override_high share every term (traits, path, aspect match)
        and differ ONLY in their real authored level (3 vs 10). If level_override
        genuinely substitutes, overriding the level-3 defender's level to 10 must
        equal the level-10 defender's own (un-overridden) rating exactly.
        """
        overridden = compute_resist_increment(self.override_low, "medium", level_override=10)
        actually_level_ten = compute_resist_increment(self.override_high, "medium")
        self.assertEqual(overridden, actually_level_ten)

    def test_level_override_substitutes_rather_than_adds(self):
        """The double-count guard: overriding to 10 must NOT equal own-level-3 result
        plus a level-10 contribution stacked on top.

        If a future change accidentally combined the override additively with the
        character's own resolved level (3), the overridden result would land far
        above the true level-10 rating -- this pins that it does not.
        """
        own_level_three = compute_resist_increment(self.override_low, "medium")
        overridden = compute_resist_increment(self.override_low, "medium", level_override=10)
        actually_level_ten = compute_resist_increment(self.override_high, "medium")

        self.assertEqual(overridden, actually_level_ten)
        double_counted = own_level_three + (actually_level_ten - own_level_three) * 2
        self.assertNotEqual(overridden, double_counted)
        # A concrete additive failure mode: own rating (level 3) plus a bare
        # LEVEL_POINTS_PER_LEVEL * 10 term stacked on top (as if level_override fed
        # an ADDED level_opposition-style term rather than substituting).
        self.assertNotEqual(overridden, own_level_three + LEVEL_POINTS_PER_LEVEL * 10)


class ResistCountsComposureModifiersTests(TestCase):
    """#4720: a defender resists with what they would bring to a Composure roll.

    Before, ``compute_resist_increment`` was rating plus effort and nothing a
    character carried on Composure rolls reached it: not Poise, not a condition.
    """

    @classmethod
    def setUpTestData(cls):
        from world.distinctions.factories import (
            CharacterDistinctionFactory,
            DistinctionEffectFactory,
            DistinctionFactory,
        )
        from world.mechanics.factories import (
            CharacterModifierFactory,
            DistinctionModifierSourceFactory,
            ModifierCategoryFactory,
            ModifierTargetFactory,
        )

        Trait.flush_instance_cache()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        cls.composure = create_resistance_check_types()["Composure"]
        willpower = StatTraitFactory(name="willpower")

        def defender():
            character = CharacterSheetFactory().character
            CharacterTraitValue.objects.create(
                character=character.sheet_data, trait=willpower, value=10
            )
            return character

        cls.plain = defender()
        cls.poised = defender()
        cls.flustered = defender()
        cls.once_only = defender()

        # Poise: a roll_modifier target scoped to the Composure check, as the seed makes it.
        cls.poise = ModifierTargetFactory(
            name="poise",
            category=ModifierCategoryFactory(name="roll_modifier"),
            target_check_type=cls.composure,
        )
        good_breeding = DistinctionFactory(name="Good Breeding")
        effect = DistinctionEffectFactory(
            distinction=good_breeding, target=cls.poise, value_per_rank=7
        )
        CharacterModifierFactory(
            character=cls.poised.sheet_data,
            value=7,
            target=cls.poise,
            source=DistinctionModifierSourceFactory(
                distinction_effect=effect,
                character_distinction=CharacterDistinctionFactory(distinction=good_breeding),
            ),
        )

        rattled = ConditionTemplateFactory(name="ResistTestFlustered")
        ConditionCheckModifierFactory(
            condition=rattled, check_type=cls.composure, modifier_value=-10
        )
        ConditionInstanceFactory(target=cls.flustered, condition=rattled)

        from world.conditions.constants import DurationType

        steeled = ConditionTemplateFactory(
            name="ResistTestSteeled", default_duration_type=DurationType.UNTIL_USED
        )
        ConditionCheckModifierFactory(condition=steeled, check_type=cls.composure, modifier_value=6)
        cls.steeled_instance = ConditionInstanceFactory(target=cls.once_only, condition=steeled)

    def setUp(self):
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()

    def test_poise_raises_resist_by_its_value(self):
        plain = compute_resist_increment(self.plain, "medium")
        poised = compute_resist_increment(self.poised, "medium")
        self.assertEqual(poised - plain, 7)

    def test_a_condition_penalty_on_composure_lowers_resist_by_its_value(self):
        plain = compute_resist_increment(self.plain, "medium")
        flustered = compute_resist_increment(self.flustered, "medium")
        self.assertEqual(plain - flustered, 10)

    def test_resist_is_the_rating_plus_effort_plus_the_gathered_modifiers(self):
        """The same sum a modifier-aware Composure roll adds, without the roll: capability
        points ride the rating, so the gathered total is the one that leaves them out."""
        from world.checks.services import collect_check_modifiers

        for character in (self.plain, self.poised, self.flustered, self.once_only):
            gathered = collect_check_modifiers(
                character.sheet_data, self.composure, skip_fashion=True
            ).extra_modifiers_total
            rating = compute_check_rating(character, self.composure)
            self.assertEqual(
                compute_resist_increment(character, "medium"),
                max(0, rating + EFFORT_CHECK_MODIFIER["medium"] + gathered),
            )

    def test_a_once_only_condition_counts_and_is_not_used_up(self):
        """Grading a difficulty is not a roll: the condition is still there afterwards."""
        from world.conditions.models import ConditionInstance

        plain = compute_resist_increment(self.plain, "medium")
        first = compute_resist_increment(self.once_only, "medium")
        second = compute_resist_increment(self.once_only, "medium")
        self.assertEqual(first - plain, 6)
        self.assertEqual(second, first)
        self.assertTrue(ConditionInstance.objects.filter(pk=self.steeled_instance.pk).exists())

    def test_more_modifier_rows_cost_no_more_queries(self):
        """The resist is graded once per target on every social check, so what it costs
        must not grow with how much the target carries."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from world.distinctions.factories import (
            CharacterDistinctionFactory,
            DistinctionEffectFactory,
            DistinctionFactory,
        )
        from world.mechanics.factories import (
            CharacterModifierFactory,
            DistinctionModifierSourceFactory,
        )

        def queries() -> int:
            Trait.flush_instance_cache()
            CharacterTraitValue.flush_instance_cache()
            with CaptureQueriesContext(connection) as captured:
                compute_resist_increment(self.poised, "medium")
            return len(captured)

        def another_poise_distinction(name: str) -> None:
            distinction = DistinctionFactory(name=name)
            effect = DistinctionEffectFactory(
                distinction=distinction, target=self.poise, value_per_rank=2
            )
            CharacterModifierFactory(
                character=self.poised.sheet_data,
                value=2,
                target=self.poise,
                source=DistinctionModifierSourceFactory(
                    distinction_effect=effect,
                    character_distinction=CharacterDistinctionFactory(distinction=distinction),
                ),
            )

        # Each count is taken warm, as a scene is: the first read after new rows refills
        # what those rows invalidated, and is not the steady cost.
        another_poise_distinction("Court Manners")
        queries()
        with_two = queries()
        for name in ("Unflappable", "Stone Faced", "Iron Nerve", "Cool Head"):
            another_poise_distinction(name)
        queries()
        self.assertEqual(queries(), with_two)

    def test_a_defender_with_no_sheet_resists_by_rating_and_effort_alone(self):
        from evennia_extensions.factories import CharacterFactory

        bare = CharacterFactory(db_key="ResistTestNoSheet")
        rating = compute_check_rating(bare, self.composure)
        self.assertEqual(
            compute_resist_increment(bare, "medium"),
            max(0, rating + EFFORT_CHECK_MODIFIER["medium"]),
        )
