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
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import (
    CharacterCodexKnowledgeFactory,
    CodexEntryFactory,
    CodexSubjectFactory,
)
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory, ThreadFactory
from world.missions.factories import MissionGiverFactory, MissionGiverStandingFactory
from world.missions.predicates import CharacterPredicateContext, evaluate
from world.roster.factories import RosterEntryFactory


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


class CharacterLevelResolverTests(TestCase):
    """min_character_level: gates on CharacterSheet.current_level."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        # Two class assignments — current_level = max() = 7
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(character=cls.character, character_class=char_class, level=3)
        CharacterClassLevelFactory(
            character=cls.character,
            character_class=CharacterClassFactory(),
            level=7,
        )
        cls.sheet.invalidate_class_level_cache()

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_true_when_at_threshold(self) -> None:
        self.assertTrue(self.ctx.has_leaf("min_character_level", level=7))

    def test_true_when_above_threshold(self) -> None:
        self.assertTrue(self.ctx.has_leaf("min_character_level", level=3))

    def test_false_when_below_threshold(self) -> None:
        self.assertFalse(self.ctx.has_leaf("min_character_level", level=8))

    def test_evaluate_dispatches(self) -> None:
        rule = {"leaf": "min_character_level", "params": {"level": 5}}
        self.assertTrue(evaluate(rule, self.ctx))
        rule_fail = {"leaf": "min_character_level", "params": {"level": 10}}
        self.assertFalse(evaluate(rule_fail, self.ctx))

    def test_zero_level_character_passes_zero_threshold(self) -> None:
        # Fresh character with no class assignments: current_level == 0.
        bare = CharacterFactory()
        CharacterSheetFactory(character=bare)
        ctx = CharacterPredicateContext(bare)
        self.assertTrue(ctx.has_leaf("min_character_level", level=0))
        self.assertFalse(ctx.has_leaf("min_character_level", level=1))


class CodexEntryResolverTests(TestCase):
    """has_codex_entry: gates on CharacterCodexKnowledge (KNOWN) for the entry.

    Authored params: ``subject`` (CodexSubject.name) + ``name`` (CodexEntry.name).
    CodexEntry uses ``unique_together = ["subject", "name"]`` so neither alone
    is a stable identifier.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.subject = CodexSubjectFactory(name="Test Subject")
        cls.known_entry = CodexEntryFactory(subject=cls.subject, name="Known Thing")
        cls.uncovered_entry = CodexEntryFactory(subject=cls.subject, name="Uncovered Thing")
        CharacterCodexKnowledgeFactory(
            roster_entry=cls.roster_entry,
            entry=cls.known_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        CharacterCodexKnowledgeFactory(
            roster_entry=cls.roster_entry,
            entry=cls.uncovered_entry,
            status=CodexKnowledgeStatus.UNCOVERED,
        )

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_true_when_known(self) -> None:
        self.assertTrue(
            self.ctx.has_leaf("has_codex_entry", subject="Test Subject", name="Known Thing")
        )

    def test_false_when_uncovered(self) -> None:
        # UNCOVERED means seen-but-not-fully-learned; the predicate gates on
        # KNOWN — the character HAS the entry, not just has heard of it.
        self.assertFalse(
            self.ctx.has_leaf("has_codex_entry", subject="Test Subject", name="Uncovered Thing")
        )

    def test_false_when_no_knowledge_row(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_codex_entry", subject="Test Subject", name="Nope"))

    def test_false_when_no_such_entry(self) -> None:
        self.assertFalse(
            self.ctx.has_leaf("has_codex_entry", subject="No Such Subject", name="Whatever")
        )

    def test_evaluate_dispatches(self) -> None:
        rule = {
            "leaf": "has_codex_entry",
            "params": {"subject": "Test Subject", "name": "Known Thing"},
        }
        self.assertTrue(evaluate(rule, self.ctx))


class ResonanceResolverTests(TestCase):
    """has_resonance: a CharacterResonance row for (sheet, resonance) exists."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.held = ResonanceFactory(name="Sylva")
        cls.unheld = ResonanceFactory(name="Praedari")
        CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.held)

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_true_when_held(self) -> None:
        self.assertTrue(self.ctx.has_leaf("has_resonance", name="Sylva"))

    def test_false_when_not_held(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_resonance", name="Praedari"))

    def test_false_when_no_such_resonance(self) -> None:
        self.assertFalse(self.ctx.has_leaf("has_resonance", name="Nonexistent"))

    def test_evaluate_dispatches(self) -> None:
        rule = {"leaf": "has_resonance", "params": {"name": "Sylva"}}
        self.assertTrue(evaluate(rule, self.ctx))


class GiverStandingResolverTests(TestCase):
    """min_giver_standing: gates on MissionGiverStanding.affection for a giver.

    The giver is referenced by slug (added in 0003); the comparison is
    affection >= ``min``. No standing row means affection is implicitly 0.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.liked_giver = MissionGiverFactory(slug="liked-giver", name="Liked")
        cls.disliked_giver = MissionGiverFactory(slug="disliked-giver", name="Disliked")
        cls.unknown_giver = MissionGiverFactory(slug="unknown-giver", name="Unknown")
        MissionGiverStandingFactory(giver=cls.liked_giver, character=cls.character, affection=50)
        MissionGiverStandingFactory(
            giver=cls.disliked_giver, character=cls.character, affection=-20
        )

    def setUp(self) -> None:
        self.ctx = CharacterPredicateContext(self.character)

    def test_true_when_at_threshold(self) -> None:
        self.assertTrue(
            self.ctx.has_leaf("min_giver_standing", giver="liked-giver", min_affection=50)
        )

    def test_true_when_above_threshold(self) -> None:
        self.assertTrue(
            self.ctx.has_leaf("min_giver_standing", giver="liked-giver", min_affection=10)
        )

    def test_false_when_below_threshold(self) -> None:
        self.assertFalse(
            self.ctx.has_leaf("min_giver_standing", giver="liked-giver", min_affection=51)
        )

    def test_negative_affection_below_zero_threshold(self) -> None:
        # disliked: affection=-20; threshold 0 must FAIL.
        self.assertFalse(
            self.ctx.has_leaf("min_giver_standing", giver="disliked-giver", min_affection=0)
        )

    def test_no_standing_row_means_zero_affection(self) -> None:
        # No standing row exists for unknown-giver/character → affection=0.
        self.assertTrue(
            self.ctx.has_leaf("min_giver_standing", giver="unknown-giver", min_affection=0)
        )
        self.assertFalse(
            self.ctx.has_leaf("min_giver_standing", giver="unknown-giver", min_affection=1)
        )

    def test_false_when_no_such_giver(self) -> None:
        # Bogus slug — the predicate fails closed rather than raising.
        self.assertFalse(
            self.ctx.has_leaf("min_giver_standing", giver="nope-doesnt-exist", min_affection=0)
        )

    def test_evaluate_dispatches(self) -> None:
        rule = {
            "leaf": "min_giver_standing",
            "params": {"giver": "liked-giver", "min_affection": 50},
        }
        self.assertTrue(evaluate(rule, self.ctx))


class SocietyStandingResolverStubTests(unittest.TestCase):
    """Stub-seal: societies standing model is persona-keyed and ambiguous."""

    @unittest.skip("stub-seam: societies standing model unverified")
    def test_min_society_standing(self) -> None:
        raise NotImplementedError
