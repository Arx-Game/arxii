"""Investigation Search-check seed — perception + Investigation (#1705)."""

from django.test import TestCase

from world.checks.models import CheckType, CheckTypeTrait
from world.clues.constants import SEARCH_CHECK_TYPE_NAME
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.investigation_checks import seed_investigation_check_content
from world.skills.models import Skill
from world.traits.models import Trait, TraitType


class InvestigationCheckSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        seed_investigation_check_content()

    def test_seeds_investigation_skill(self) -> None:
        skill = Skill.objects.get(trait__name="Investigation")
        self.assertEqual(skill.trait.trait_type, TraitType.SKILL)

    def test_search_check_is_perception_plus_investigation(self) -> None:
        search = CheckType.objects.get(name=SEARCH_CHECK_TYPE_NAME)
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=search).values_list("trait__name", flat=True)
        )
        self.assertEqual(trait_names, {"perception", "Investigation"})
        # perception is a stat, Investigation is the skill leg — the tenet's stat + skill shape.
        self.assertEqual(Trait.objects.get(name="Investigation").trait_type, TraitType.SKILL)
        self.assertEqual(Trait.objects.get(name="perception").trait_type, TraitType.STAT)

    def test_idempotent(self) -> None:
        seed_investigation_check_content()
        seed_investigation_check_content()
        search = CheckType.objects.get(name=SEARCH_CHECK_TYPE_NAME)
        # Authoritative re-seed leaves exactly the two composition rows (no duplicates).
        self.assertEqual(CheckTypeTrait.objects.filter(check_type=search).count(), 2)


class LockpickingCheckSeedTests(TestCase):
    """Lockpicking CheckType seed — wits + Skulduggery (#2176)."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_check_resolution_tables()
        seed_investigation_check_content()

    def test_ensure_lockpicking_check_creates_check_type(self) -> None:
        from world.seeds.investigation_checks import ensure_lockpicking_check

        check_type = ensure_lockpicking_check()
        self.assertEqual(check_type.name, "Lockpicking")
        self.assertTrue(check_type.is_active)
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=check_type).values_list(
                "trait__name", flat=True
            )
        )
        self.assertEqual(trait_names, {"wits", "Skulduggery"})
        self.assertEqual(Trait.objects.get(name="Skulduggery").trait_type, TraitType.SKILL)
        self.assertEqual(Trait.objects.get(name="wits").trait_type, TraitType.STAT)

    def test_ensure_lockpicking_check_is_idempotent(self) -> None:
        from world.seeds.investigation_checks import ensure_lockpicking_check

        first = ensure_lockpicking_check()
        second = ensure_lockpicking_check()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CheckTypeTrait.objects.filter(check_type=first).count(), 2)
