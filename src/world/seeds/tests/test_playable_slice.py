"""Bounded playable-slice proof for the Phase A seed loader (#651).

Seeds the full dev database (now including the check-resolution spine) and
proves that a freshly seeded DB resolves a real check to a real CheckOutcome.
Scope is deliberately narrow: resolution tables + combat content + a single
factory-built character's check resolving. The full character-creation
pipeline and a live multi-round encounter are Phase 2, out of scope here.
"""

from django.test import TestCase

from world.seeds.database import seed_dev_database


class TestPlayableSlice(TestCase):
    def test_resolution_tables_seeded(self) -> None:
        from world.traits.models import CheckRank, ResultChart

        seed_dev_database()
        self.assertGreater(CheckRank.objects.count(), 0)
        self.assertGreater(ResultChart.objects.count(), 0)

    def test_combat_resolution_content_present(self) -> None:
        from world.checks.models import CheckType

        seed_dev_database()
        # penetration + flee CheckTypes seeded by the combat cluster
        self.assertTrue(CheckType.objects.filter(name__in=["penetration", "flee"]).exists())

    def test_a_factory_character_check_resolves_to_a_real_outcome(self) -> None:
        """A factory character's check resolves to a real CheckOutcome.

        Mirrors world/checks/tests/test_services.py PerformCheckTests: seed the
        DB, build a character with an existing factory, give it a trait value
        for a trait the seeded ``flee`` CheckType weights, then call the live
        ``perform_check`` and assert a real (non-null) CheckOutcome comes back.
        """
        from evennia_extensions.factories import CharacterFactory
        from world.checks.models import CheckType, CheckTypeTrait
        from world.checks.services import perform_check
        from world.checks.types import CheckResult
        from world.traits.models import (
            CharacterTraitValue,
            CheckOutcome,
            ResultChart,
            Trait,
        )

        seed_dev_database()
        ResultChart.clear_cache()
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()

        # The seeded "flee" CheckType weights real STAT traits (agility/wits).
        flee = CheckType.objects.get(name="flee")
        weighted_trait = (
            CheckTypeTrait.objects.filter(check_type=flee).select_related("trait").first()
        )
        self.assertIsNotNone(weighted_trait)
        trait = weighted_trait.trait

        character = CharacterFactory()
        CharacterTraitValue.objects.create(character=character, trait=trait, value=30)

        result = perform_check(character, flee, target_difficulty=0)

        self.assertIsInstance(result, CheckResult)
        self.assertGreater(result.trait_points, 0)
        self.assertIsNotNone(result.outcome)
        self.assertIsInstance(result.outcome, CheckOutcome)
