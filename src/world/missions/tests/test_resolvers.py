"""Tests for the missions leaf-resolver registry (Phase 0.3).

Each resolver tests one slice of the acting character's *own durable state*.
Tests build real factory objects (never mock the ORM) and exercise the
resolver both through the registry/``CharacterPredicateContext`` and through
the full ``evaluate`` rule tree, so the structural layer and the leaf layer
are verified together.

``min_society_standing`` is stub-sealed: ``world.societies`` reputation is
keyed by ``scenes.Persona`` (not character/sheet), and "standing" is
ambiguous across SocietyReputation / OrganizationReputation / membership
rank with no defined character->persona selection rule. Its test is skipped
until the societies standing model is verified (DESIGN §4).
"""

import unittest

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.magic.factories import ThreadFactory
from world.missions.predicates import CharacterPredicateContext, evaluate


class DistinctionAchievementResolverTests(TestCase):
    """has_distinction (ObjectDB-keyed) and has_achievement (sheet-keyed)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.distinction = DistinctionFactory(slug="brave")
        CharacterDistinctionFactory(character=cls.character, distinction=cls.distinction)
        cls.achievement = AchievementFactory(slug="first-blood")
        CharacterAchievementFactory(
            character_sheet=cls.sheet,
            achievement=cls.achievement,
        )

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_has_distinction_true_when_owned(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_distinction", slug="brave"))

    def test_has_distinction_false_when_not_owned(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_distinction", slug="craven"))

    def test_has_achievement_true_when_earned(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_achievement", slug="first-blood"))

    def test_has_achievement_false_when_not_earned(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_achievement", slug="last-stand"))

    def test_evaluate_composes_distinction_and_achievement(self) -> None:
        rule = {
            "op": "AND",
            "of": [
                {"leaf": "has_distinction", "params": {"slug": "brave"}},
                {"leaf": "has_achievement", "params": {"slug": "first-blood"}},
            ],
        }
        self.assertIs(evaluate(rule, self.ctx), True)

        missing = {
            "op": "AND",
            "of": [
                {"leaf": "has_distinction", "params": {"slug": "brave"}},
                {"leaf": "has_achievement", "params": {"slug": "nope"}},
            ],
        }
        self.assertIs(evaluate(missing, self.ctx), False)


class ConditionCapabilityResolverTests(TestCase):
    """has_condition (ObjectDB-keyed instance) and has_capability (>0 value)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.condition = ConditionTemplateFactory(name="Blessed")
        ConditionInstanceFactory(target=cls.character, condition=cls.condition)

        # A capability granted (positive value) by an active condition.
        cls.capability = CapabilityTypeFactory(name="nightvision")
        cls.cap_condition = ConditionTemplateFactory(name="Owl Sight")
        ConditionCapabilityEffectFactory(
            condition=cls.cap_condition,
            capability=cls.capability,
            value=10,
        )
        ConditionInstanceFactory(target=cls.character, condition=cls.cap_condition)

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_has_condition_true_when_present(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_condition", key="Blessed"))

    def test_has_condition_false_when_absent(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_condition", key="Cursed"))

    def test_has_condition_false_when_suppressed(self) -> None:
        """A suppressed ConditionInstance row exists but must not gate True."""
        from datetime import timedelta

        from django.utils import timezone

        suppressed_template = ConditionTemplateFactory(name="Hexed")
        ConditionInstanceFactory(
            target=self.character,
            condition=suppressed_template,
            is_suppressed=True,
            suppressed_until=timezone.now() + timedelta(days=1),
        )
        self.assertFalse(self.ctx.has_leaf("has_condition", key="Hexed"))

    def test_has_capability_true_when_granted(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_capability", name="nightvision"))

    def test_has_capability_false_when_unknown(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_capability", name="flight"))


class ThreadResolverTests(TestCase):
    """has_thread / min_thread_level — owner is a CharacterSheet."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.thread = ThreadFactory(owner=cls.sheet, level=30)

        cls.other = CharacterFactory()
        cls.other_sheet = CharacterSheetFactory(character=cls.other)

    def test_has_thread_true_when_owner_has_one(self) -> None:
        ctx = CharacterPredicateContext(self.character)
        self.assertTrue(ctx.has_leaf("has_thread"))

    def test_has_thread_false_when_none(self) -> None:
        ctx = CharacterPredicateContext(self.other)
        self.assertFalse(ctx.has_leaf("has_thread"))

    def test_min_thread_level_true_when_met(self) -> None:
        ctx = CharacterPredicateContext(self.character)
        self.assertTrue(ctx.has_leaf("min_thread_level", level=30))
        self.assertTrue(ctx.has_leaf("min_thread_level", level=20))

    def test_min_thread_level_false_when_below(self) -> None:
        ctx = CharacterPredicateContext(self.character)
        self.assertFalse(ctx.has_leaf("min_thread_level", level=40))


class TraitResolverTests(TestCase):
    """min_trait / has_skill — CharacterTraitValue keyed by ObjectDB."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.traits.factories import (
            CharacterTraitValueFactory,
            SkillTraitFactory,
            StatTraitFactory,
        )

        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

        cls.strength = StatTraitFactory(name="strength")
        CharacterTraitValueFactory(
            character=cls.character,
            trait=cls.strength,
            value=45,
        )
        cls.sewing = SkillTraitFactory(name="sewing")
        CharacterTraitValueFactory(
            character=cls.character,
            trait=cls.sewing,
            value=20,
        )

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_min_trait_true_when_met(self) -> None:
        self.assertTrue(self.ctx.has_leaf("min_trait", trait="strength", value=45))
        self.assertTrue(self.ctx.has_leaf("min_trait", trait="strength", value=10))

    def test_min_trait_false_when_below_or_absent(self) -> None:
        self.assertFalse(self.ctx.has_leaf("min_trait", trait="strength", value=46))
        self.assertFalse(self.ctx.has_leaf("min_trait", trait="charm", value=1))

    def test_has_skill_true_when_present(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_skill", skill="sewing"))

    def test_has_skill_false_when_absent(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_skill", skill="smithing"))


class SocietyStandingResolverStubTests(unittest.TestCase):
    """Stub-seal: societies standing model is persona-keyed and ambiguous."""

    @unittest.skip("stub-seam: societies standing model unverified")
    def test_min_society_standing(self) -> None:
        raise NotImplementedError
