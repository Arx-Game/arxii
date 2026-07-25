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
from world.conditions.factories import CapabilityTypeFactory
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

    def test_resist_increment_now_carries_aspect_specialization_and_capability(self):
        """Gap 1: the resist side was trait-points-only."""
        bare = compute_resist_increment(self.plain_defender, "medium")
        rich = compute_resist_increment(self.decorated_defender, "medium")
        self.assertGreater(rich, bare)

    def test_resist_increment_is_exactly_rating_plus_effort(self):
        """compute_resist_increment adds no term beyond the Composure rating + effort.

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
