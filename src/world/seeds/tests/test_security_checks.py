"""Security check seed — Skulduggery/Athletics skills + security check compositions (#2180).

Skulduggery was born "Larceny" (#2180) and renamed with its criminal specializations in
#1825 — the seed renames a pre-existing Larceny row in place (preserving FKs) before
ensuring, so old dev DBs converge.
"""

from django.test import TestCase

from world.checks.models import CheckType, CheckTypeTrait
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.security_checks import seed_security_check_content
from world.seeds.stealth_checks import seed_stealth_check_content


class SecurityCheckSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_check_resolution_tables()
        seed_stealth_check_content()
        seed_security_check_content()

    def test_seeds_skulduggery_skill(self):
        from world.skills.models import Skill
        from world.traits.models import TraitCategory, TraitType

        skill = Skill.objects.get(trait__name="Skulduggery")
        assert skill.trait.trait_type == TraitType.SKILL
        assert skill.trait.category == TraitCategory.PHYSICAL

    def test_no_larceny_skill_remains(self):
        from world.traits.models import Trait

        assert not Trait.objects.filter(name="Larceny").exists()

    def test_seeds_athletics_skill(self):
        from world.skills.models import Skill
        from world.traits.models import TraitCategory, TraitType

        skill = Skill.objects.get(trait__name="Athletics")
        assert skill.trait.trait_type == TraitType.SKILL
        assert skill.trait.category == TraitCategory.PHYSICAL

    def test_seeds_lockpicking_under_skulduggery(self):
        from world.skills.models import Specialization

        spec = Specialization.objects.get(
            name="Lockpicking", parent_skill__trait__name="Skulduggery"
        )
        assert spec.is_active

    def test_seeds_criminal_specializations(self):
        """#1825: the five criminal specializations hang off Skulduggery."""
        from world.skills.models import Specialization

        for name in ["Pickpocketing", "Streetwise", "Disguise", "Forgery", "Sleight of Hand"]:
            spec = Specialization.objects.get(name=name, parent_skill__trait__name="Skulduggery")
            assert spec.is_active, name

    def test_seeds_climbing_under_athletics(self):
        from world.skills.models import Specialization

        spec = Specialization.objects.get(name="Climbing", parent_skill__trait__name="Athletics")
        assert spec.is_active

    def test_lockpick_composition(self):
        from world.checks.models import CheckTypeSpecialization, CheckTypeTrait

        ct = CheckType.objects.get(name="Lockpick")
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=ct).values_list("trait__name", flat=True)
        )
        assert trait_names == {"wits", "Skulduggery"}
        spec_names = set(
            CheckTypeSpecialization.objects.filter(check_type=ct).values_list(
                "specialization__name", flat=True
            )
        )
        assert spec_names == {"Lockpicking"}

    def test_forge_evidence_composition(self):
        """#1825: the frame-job tamper check — wits + Skulduggery + Forgery."""
        from world.checks.models import CheckTypeSpecialization, CheckTypeTrait

        ct = CheckType.objects.get(name="Forge Evidence")
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=ct).values_list("trait__name", flat=True)
        )
        assert trait_names == {"wits", "Skulduggery"}
        spec_names = set(
            CheckTypeSpecialization.objects.filter(check_type=ct).values_list(
                "specialization__name", flat=True
            )
        )
        assert spec_names == {"Forgery"}

    def test_gather_evidence_composition(self):
        """#1825: the at-the-scene evidence claim check — wits + Skulduggery, no spec."""
        from world.checks.models import CheckTypeSpecialization, CheckTypeTrait

        ct = CheckType.objects.get(name="Gather Evidence")
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=ct).values_list("trait__name", flat=True)
        )
        assert trait_names == {"wits", "Skulduggery"}
        assert not CheckTypeSpecialization.objects.filter(check_type=ct).exists()

    def test_scrutinize_evidence_composition(self):
        """#1825: the case-file examine check — perception + Investigation, no spec."""
        from world.checks.models import CheckTypeSpecialization, CheckTypeTrait

        ct = CheckType.objects.get(name="Scrutinize Evidence")
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=ct).values_list("trait__name", flat=True)
        )
        assert trait_names == {"perception", "Investigation"}
        assert not CheckTypeSpecialization.objects.filter(check_type=ct).exists()
        assert ct.category.name == "Exploration"

    def test_break_and_enter_composition(self):
        from world.checks.models import CheckTypeSpecialization, CheckTypeTrait

        ct = CheckType.objects.get(name="Break and Enter")
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=ct).values_list("trait__name", flat=True)
        )
        assert trait_names == {"strength", "Athletics"}
        assert not CheckTypeSpecialization.objects.filter(check_type=ct).exists()

    def test_escape_through_window_composition(self):
        from world.checks.models import CheckTypeSpecialization, CheckTypeTrait

        ct = CheckType.objects.get(name="Escape Through Window")
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=ct).values_list("trait__name", flat=True)
        )
        assert trait_names == {"agility", "Athletics"}
        spec_names = set(
            CheckTypeSpecialization.objects.filter(check_type=ct).values_list(
                "specialization__name", flat=True
            )
        )
        assert spec_names == {"Climbing"}

    def test_guard_detection_composition(self):
        from world.checks.models import CheckTypeSpecialization, CheckTypeTrait

        ct = CheckType.objects.get(name="Guard Detection")
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=ct).values_list("trait__name", flat=True)
        )
        assert trait_names == {"perception", "Investigation"}
        assert not CheckTypeSpecialization.objects.filter(check_type=ct).exists()

    def test_guard_detection_in_exploration_category(self):
        ct = CheckType.objects.get(name="Guard Detection")
        assert ct.category.name == "Exploration"

    def test_reseed_is_authoritative(self):
        from world.traits.models import Trait, TraitType

        lockpick = CheckType.objects.get(name="Lockpick")
        stray = Trait.objects.create(name="stray_stat", trait_type=TraitType.STAT)
        CheckTypeTrait.objects.create(check_type=lockpick, trait=stray)
        seed_security_check_content()
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=lockpick).values_list("trait__name", flat=True)
        )
        assert trait_names == {"wits", "Skulduggery"}

    def test_reseed_is_idempotent(self):
        seed_security_check_content()
        seed_security_check_content()
        assert CheckType.objects.filter(name="Lockpick").count() == 1
        assert CheckType.objects.filter(name="Break and Enter").count() == 1
        assert CheckType.objects.filter(name="Escape Through Window").count() == 1
        assert CheckType.objects.filter(name="Guard Detection").count() == 1
        assert CheckType.objects.filter(name="Forge Evidence").count() == 1
        assert CheckType.objects.filter(name="Gather Evidence").count() == 1
        assert CheckType.objects.filter(name="Scrutinize Evidence").count() == 1


class SkulduggeryRenameTests(TestCase):
    """The seed renames a pre-existing Larceny row in place (#1825) — FKs survive."""

    def test_rename_converges_from_larceny(self):
        from world.skills.models import Skill
        from world.traits.models import Trait, TraitCategory, TraitType

        trait = Trait.objects.create(
            name="Larceny",
            trait_type=TraitType.SKILL,
            category=TraitCategory.PHYSICAL,
            is_public=True,
        )
        skill = Skill.objects.create(trait=trait, tooltip="old", display_order=35, is_active=True)

        seed_check_resolution_tables()
        seed_stealth_check_content()
        seed_security_check_content()

        # No refresh needed: Trait is identity-mapped, so the seed mutated THIS instance.
        assert trait.name == "Skulduggery"
        assert Trait.objects.filter(pk=trait.pk, name="Skulduggery").exists()
        assert Skill.objects.get(trait=trait).pk == skill.pk
        assert not Trait.objects.filter(name="Larceny").exists()
        assert Trait.objects.filter(name="Skulduggery").count() == 1
