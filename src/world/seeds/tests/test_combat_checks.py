"""Melee Combat skill catalog + Melee Attack check composition (#1706)."""

from django.test import TestCase, override_settings

from world.seeds.combat_checks import seed_combat_check_content


@override_settings(SEED_SAMPLE_CONTENT=True)  # seed_combat_check_content gates on #2698
class CombatCheckSeedTests(TestCase):
    def test_melee_combat_skill_seeded(self):
        from world.skills.models import Skill
        from world.traits.models import TraitCategory, TraitType

        seed_combat_check_content()
        skill = Skill.objects.get(trait__name="Melee Combat")
        self.assertEqual(skill.trait.trait_type, TraitType.SKILL)
        self.assertEqual(skill.trait.category, TraitCategory.COMBAT)

    def test_weapon_specializations_seeded(self):
        from world.skills.models import Specialization

        seed_combat_check_content()
        specs = {
            s.name for s in Specialization.objects.filter(parent_skill__trait__name="Melee Combat")
        }
        self.assertEqual(specs, {"Small Weapons", "Medium Weapons", "Heavy Weapons"})

    def test_melee_attack_composition(self):
        from world.checks.models import (
            CheckType,
        )

        seed_combat_check_content()
        ct = CheckType.objects.get(name="Melee Combat")
        trait_names = {t.trait.name for t in ct.traits.all()}  # type: ignore[attr-defined]
        self.assertEqual(trait_names, {"strength", "Melee Combat"})
        spec_names = {
            s.specialization.name
            for s in ct.specializations.all()  # type: ignore[attr-defined]
        }
        self.assertEqual(spec_names, {"Small Weapons", "Medium Weapons", "Heavy Weapons"})

    def test_seed_is_idempotent(self):
        from world.checks.models import CheckType

        seed_combat_check_content()
        seed_combat_check_content()  # re-run
        self.assertEqual(CheckType.objects.filter(name="Melee Combat").count(), 1)

    def test_melee_combat_is_single_check(self):
        """#2757: Melee Attack + Melee Defense merged into one 'Melee Combat' CheckType."""
        from world.checks.models import CheckType

        seed_combat_check_content()
        # No separate Melee Defense CheckType exists anymore
        self.assertFalse(CheckType.objects.filter(name="Melee Defense").exists())
        self.assertEqual(CheckType.objects.filter(name="Melee Combat").count(), 1)
