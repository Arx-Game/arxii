"""Governance seed — Scholarship/Economics + Organization/Stewardship + checks (#930)."""

from django.test import TestCase

from world.checks.models import CheckType, CheckTypeSpecialization, CheckTypeTrait
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.governance_checks import seed_governance_check_content
from world.skills.models import Skill, Specialization
from world.traits.models import Trait, TraitType


class GovernanceCheckSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        seed_governance_check_content()

    def test_seeds_both_skills_with_their_specs(self) -> None:
        for skill_name, spec_name in (
            ("Scholarship", "Economics"),
            ("Leadership", "Stewardship"),
        ):
            skill = Skill.objects.get(trait__name=skill_name)
            self.assertEqual(skill.trait.trait_type, TraitType.SKILL)
            Specialization.objects.get(parent_skill=skill, name=spec_name)

    def test_tax_collection_composition(self) -> None:
        check = CheckType.objects.get(name="Tax Collection")
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=check).values_list("trait__name", flat=True)
        )
        self.assertEqual(trait_names, {"presence", "Leadership"})
        spec = CheckTypeSpecialization.objects.get(check_type=check)
        self.assertEqual(spec.specialization.name, "Stewardship")

    def test_domain_investment_composition(self) -> None:
        check = CheckType.objects.get(name="Domain Investment")
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=check).values_list("trait__name", flat=True)
        )
        self.assertEqual(trait_names, {"intellect", "Scholarship"})
        spec = CheckTypeSpecialization.objects.get(check_type=check)
        self.assertEqual(spec.specialization.name, "Economics")
        self.assertEqual(Trait.objects.get(name="intellect").trait_type, TraitType.STAT)

    def test_idempotent(self) -> None:
        seed_governance_check_content()
        seed_governance_check_content()
        check = CheckType.objects.get(name="Tax Collection")
        self.assertEqual(CheckTypeTrait.objects.filter(check_type=check).count(), 2)
        self.assertEqual(CheckTypeSpecialization.objects.filter(check_type=check).count(), 1)
