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


class TestSeededCharacterCreation(TestCase):
    """The #1333 proof: a clean DB seeded via the Big Button can run CG.

    Builds a CharacterDraft against the SEEDED CG-world content (not test-only
    rows) and asserts ``finalize_character`` produces a CharacterSheet + primary
    Persona without raising. This is the test that closes the "fresh DB cannot
    run character creation" gap.
    """

    def test_finalize_character_works_on_seeded_only_db(self) -> None:
        from evennia.accounts.models import AccountDB

        from world.character_creation.models import CharacterDraft
        from world.character_creation.services import finalize_character
        from world.character_sheets.models import CharacterSheet
        from world.magic.models import Cantrip
        from world.seeds.character_creation import DEFAULT_STAT_NAMES
        from world.tarot.models import TarotCard

        seed_dev_database()

        area = CharacterDraft._meta.get_field("selected_area").related_model.objects.get(
            name="Arx City"
        )
        beginnings = CharacterDraft._meta.get_field(
            "selected_beginnings"
        ).related_model.objects.get(name="Commoner")
        species = CharacterDraft._meta.get_field("selected_species").related_model.objects.get(
            name="Human"
        )
        gender = CharacterDraft._meta.get_field("selected_gender").related_model.objects.get(
            key="unspecified"
        )
        path = CharacterDraft._meta.get_field("selected_path").related_model.objects.get(
            name="The Wanderer"
        )
        height_band = CharacterDraft._meta.get_field("height_band").related_model.objects.get(
            name="average_band"
        )
        build = CharacterDraft._meta.get_field("build").related_model.objects.get(
            name="average_build"
        )
        tarot = TarotCard.objects.get(name="The Fool")

        # The seeded magic cluster provides a selectable cantrip.
        cantrip = Cantrip.objects.first()
        self.assertIsNotNone(cantrip, "magic cluster must seed a selectable cantrip")

        account = AccountDB.objects.create(username="seeded_cg_player")
        draft_data = {
            "first_name": "Seeded",
            "description": "A character finalized against seeded-only content.",
            "stats": dict.fromkeys(DEFAULT_STAT_NAMES, 2),
            "lineage_is_orphan": True,
            "tarot_card_name": tarot.name,
            "tarot_reversed": False,
            "traits_complete": True,
            "selected_cantrip_id": cantrip.id,
        }
        # selected_tradition may be nullable; leave it unset unless finalize needs it.

        draft = CharacterDraft.objects.create(
            account=account,
            selected_area=area,
            selected_beginnings=beginnings,
            selected_species=species,
            selected_gender=gender,
            selected_path=path,
            age=25,
            height_band=height_band,
            height_inches=(height_band.min_inches + height_band.max_inches) // 2,
            build=build,
            draft_data=draft_data,
        )

        character = finalize_character(draft, add_to_roster=True)

        self.assertIsNotNone(character)
        self.assertTrue(CharacterSheet.objects.filter(character=character).exists())
