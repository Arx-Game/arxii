"""Melee Combat skill catalog + Melee Attack check composition (#1706)."""

from django.test import TestCase

from world.seeds.combat_checks import seed_combat_check_content


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
        ct = CheckType.objects.get(name="Melee Attack")
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
        self.assertEqual(CheckType.objects.filter(name="Melee Attack").count(), 1)

    def test_melee_defense_composition(self):
        from world.checks.models import CheckType

        seed_combat_check_content()
        ct = CheckType.objects.get(name="Melee Defense")
        trait_names = {t.trait.name for t in ct.traits.all()}
        self.assertEqual(trait_names, {"agility", "Melee Combat"})
        spec_names = {s.specialization.name for s in ct.specializations.all()}
        self.assertEqual(spec_names, {"Small Weapons", "Medium Weapons", "Heavy Weapons"})

    def test_melee_defense_idempotent(self):
        from world.checks.models import CheckType

        seed_combat_check_content()
        seed_combat_check_content()
        self.assertEqual(CheckType.objects.filter(name="Melee Defense").count(), 1)
