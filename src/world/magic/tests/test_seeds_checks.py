"""Tests for world.magic.seeds_checks (#709, #4547)."""

from decimal import Decimal

from django.test import TestCase, override_settings

from world.checks.models import CheckCategory, CheckType, CheckTypeAspect, CheckTypeTrait
from world.classes.models import Aspect
from world.magic.constants import MagicActivity
from world.magic.factories import MagicActivitySkillFactory, map_ritual_working_skill
from world.magic.seeds_checks import (
    ANIMA_RESTORATION_CHECK_TYPE_NAME,
    MAGIC_CHECK_CATEGORY_NAME,
    ensure_magic_check_content,
    ensure_magic_check_types,
    ensure_ritual_check_configs,
)
from world.magic.seeds_sanctum import (
    DISSOLUTION_RITUAL_NAME,
    ensure_sanctum_rituals,
)
from world.skills.factories import MagicSkillFactory
from world.skills.models import Skill
from world.traits.models import Trait, TraitType


@override_settings(SEED_SAMPLE_CONTENT=True)  # sampling on: the seed may invent rows
class FreshSeedCreatesNoMagicSkillTests(TestCase):
    """No skill is named, created or weighted for magic by the seed (#4547, ADR-4450)."""

    def test_the_umbrella_seed_creates_and_weights_no_skill(self):
        ensure_sanctum_rituals()
        ensure_magic_check_content()

        self.assertFalse(Skill.objects.exists())
        self.assertFalse(Trait.objects.filter(trait_type=TraitType.SKILL).exists())
        self.assertFalse(CheckTypeTrait.objects.filter(trait__trait_type=TraitType.SKILL).exists())


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_magic_check_types gates on #2698
class EnsureMagicCheckTypesTests(TestCase):
    def test_creates_six_composed_check_types(self):
        check_types = ensure_magic_check_types()
        self.assertEqual(len(check_types), 6)
        category = CheckCategory.objects.get(name=MAGIC_CHECK_CATEGORY_NAME)
        arcana = Aspect.objects.get(name="Arcana")
        for ct in check_types.values():
            self.assertEqual(ct.category_id, category.pk)
            cta = CheckTypeAspect.objects.get(check_type=ct, aspect=arcana)
            self.assertEqual(cta.weight, Decimal("1.00"))
            traits = CheckTypeTrait.objects.filter(check_type=ct)
            self.assertEqual(traits.count(), 1)
            self.assertEqual(traits.get().trait.trait_type, TraitType.STAT)

    def test_dissolution_composition(self):
        check_types = ensure_magic_check_types()
        ct = check_types["Sanctum Dissolution"]
        weights = {
            row.trait.name: row.weight for row in CheckTypeTrait.objects.filter(check_type=ct)
        }
        self.assertEqual(weights, {"willpower": Decimal("1.00")})

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
            6,
        )


@override_settings(SEED_SAMPLE_CONTENT=True)
class EnsureRitualCheckConfigsTests(TestCase):
    def test_creates_configs_for_all_five_service_rituals(self):
        mapped = map_ritual_working_skill()
        ensure_sanctum_rituals()
        configs = ensure_ritual_check_configs()
        self.assertEqual(len(configs), 5)
        dissolution = configs[DISSOLUTION_RITUAL_NAME]
        self.assertEqual(dissolution.target_difficulty, 20)
        self.assertEqual(dissolution.non_founder_target_difficulty, 40)
        self.assertEqual(dissolution.check_type.name, "Sanctum Dissolution")
        self.assertEqual(dissolution.stat.name, "willpower")
        self.assertEqual(dissolution.skill, mapped.skill)

    def test_no_ritual_working_skill_writes_no_config(self):
        """The seed names no skill: with ritual working unmapped there is none to use."""
        MagicActivitySkillFactory(activity=MagicActivity.CEREMONY, skill=MagicSkillFactory())
        ensure_sanctum_rituals()

        self.assertEqual(ensure_ritual_check_configs(), {})

    def test_an_inactive_ritual_working_skill_is_not_used(self):
        MagicActivitySkillFactory(
            activity=MagicActivity.RITUAL_WORKING, skill=MagicSkillFactory(is_active=False)
        )
        ensure_sanctum_rituals()

        self.assertEqual(ensure_ritual_check_configs(), {})

    def test_idempotent_and_preserves_tuning(self):
        map_ritual_working_skill()
        ensure_sanctum_rituals()
        configs = ensure_ritual_check_configs()
        dissolution = configs[DISSOLUTION_RITUAL_NAME]
        dissolution.target_difficulty = 99
        dissolution.save(update_fields=["target_difficulty"])
        configs = ensure_ritual_check_configs()
        self.assertEqual(configs[DISSOLUTION_RITUAL_NAME].target_difficulty, 99)

    def test_skips_configs_if_rituals_not_seeded(self):
        """Ritual rows are content-repo-owned (#2698): a missing ritual is
        skipped (logged), not a raised ``DoesNotExist`` — mirrors
        ``ensure_sanctum_rituals()``'s own skip-on-missing behavior.
        """
        # ensure_sanctum_rituals() intentionally not called; Ritual rows absent.
        configs = ensure_ritual_check_configs()
        self.assertEqual(configs, {})


@override_settings(SEED_SAMPLE_CONTENT=True)
class EnsureMagicCheckContentTests(TestCase):
    def test_umbrella_runs_end_to_end(self):
        map_ritual_working_skill()
        ensure_sanctum_rituals()
        result = ensure_magic_check_content()
        self.assertIn(ANIMA_RESTORATION_CHECK_TYPE_NAME, result.check_types)
        self.assertEqual(len(result.configs), 5)
