"""Tests for world.magic.seeds_checks (#709)."""

from decimal import Decimal

from django.test import TestCase

from world.checks.models import CheckCategory, CheckType, CheckTypeAspect, CheckTypeTrait
from world.classes.models import Aspect
from world.magic.seeds_checks import (
    ANIMA_RESTORATION_CHECK_TYPE_NAME,
    MAGIC_CHECK_CATEGORY_NAME,
    ensure_magic_check_content,
    ensure_magic_check_types,
    ensure_magic_skills,
    ensure_ritual_check_configs,
)
from world.magic.seeds_sanctum import (
    DISSOLUTION_RITUAL_NAME,
    ensure_sanctum_rituals,
)
from world.skills.models import Skill
from world.traits.models import Trait, TraitType


class EnsureMagicSkillsTests(TestCase):
    def test_creates_three_skills_with_backing_traits(self):
        skills = ensure_magic_skills()
        self.assertEqual(set(skills), {"ritualism", "occult", "theology"})
        for name, skill in skills.items():
            self.assertIsInstance(skill, Skill)
            self.assertEqual(skill.trait.name, name)
            self.assertEqual(skill.trait.trait_type, TraitType.SKILL)

    def test_idempotent(self):
        first = ensure_magic_skills()
        second = ensure_magic_skills()
        self.assertEqual(
            {k: v.pk for k, v in first.items()},
            {k: v.pk for k, v in second.items()},
        )
        self.assertEqual(Trait.objects.filter(name="ritualism").count(), 1)


class EnsureMagicCheckTypesTests(TestCase):
    def test_creates_five_composed_check_types(self):
        check_types = ensure_magic_check_types()
        self.assertEqual(len(check_types), 5)
        category = CheckCategory.objects.get(name=MAGIC_CHECK_CATEGORY_NAME)
        arcana = Aspect.objects.get(name="Arcana")
        for ct in check_types.values():
            self.assertEqual(ct.category_id, category.pk)
            self.assertTrue(CheckTypeAspect.objects.filter(check_type=ct, aspect=arcana).exists())
            self.assertGreaterEqual(CheckTypeTrait.objects.filter(check_type=ct).count(), 2)

    def test_dissolution_composition(self):
        check_types = ensure_magic_check_types()
        ct = check_types["Sanctum Dissolution"]
        weights = {
            row.trait.name: row.weight for row in CheckTypeTrait.objects.filter(check_type=ct)
        }
        self.assertEqual(weights["willpower"], Decimal("1.00"))
        self.assertEqual(weights["occult"], Decimal("1.00"))
        self.assertEqual(weights["ritualism"], Decimal("0.50"))

    def test_placeholder_description_replaced_but_edits_preserved(self):
        category, _ = CheckCategory.objects.get_or_create(
            name=MAGIC_CHECK_CATEGORY_NAME,
            defaults={"description": "PLACEHOLDER — Magic checks (Plan 4 §F)."},
        )
        CheckType.objects.get_or_create(
            name="Sanctum Dissolution",
            category=category,
            defaults={"description": "PLACEHOLDER — Sanctum Dissolution check."},
        )
        ensure_magic_check_types()
        ct = CheckType.objects.get(name="Sanctum Dissolution")
        self.assertFalse(ct.description.startswith("PLACEHOLDER"))
        # A staff-edited description must survive a re-run.
        ct.description = "Staff-tuned description."
        ct.save(update_fields=["description"])
        ensure_magic_check_types()
        ct = CheckType.objects.get(name="Sanctum Dissolution")
        self.assertEqual(ct.description, "Staff-tuned description.")

    def test_idempotent(self):
        ensure_magic_check_types()
        ensure_magic_check_types()
        self.assertEqual(
            CheckType.objects.filter(category__name=MAGIC_CHECK_CATEGORY_NAME).count(),
            5,
        )


class EnsureRitualCheckConfigsTests(TestCase):
    def test_creates_configs_for_all_five_service_rituals(self):
        ensure_sanctum_rituals()
        configs = ensure_ritual_check_configs()
        self.assertEqual(len(configs), 5)
        dissolution = configs[DISSOLUTION_RITUAL_NAME]
        self.assertEqual(dissolution.target_difficulty, 20)
        self.assertEqual(dissolution.non_founder_target_difficulty, 40)
        self.assertEqual(dissolution.check_type.name, "Sanctum Dissolution")

    def test_idempotent_and_preserves_tuning(self):
        ensure_sanctum_rituals()
        configs = ensure_ritual_check_configs()
        dissolution = configs[DISSOLUTION_RITUAL_NAME]
        dissolution.target_difficulty = 99
        dissolution.save(update_fields=["target_difficulty"])
        configs = ensure_ritual_check_configs()
        self.assertEqual(configs[DISSOLUTION_RITUAL_NAME].target_difficulty, 99)


class EnsureMagicCheckContentTests(TestCase):
    def test_umbrella_runs_end_to_end(self):
        ensure_sanctum_rituals()
        result = ensure_magic_check_content()
        self.assertIn(ANIMA_RESTORATION_CHECK_TYPE_NAME, result.check_types)
        self.assertEqual(len(result.skills), 3)
        self.assertEqual(len(result.configs), 5)
