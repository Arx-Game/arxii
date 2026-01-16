"""
Tests for character creation services.
"""

from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from evennia.accounts.models import AccountDB

from world.character_creation.models import CharacterDraft, SpeciesOption, StartingArea
from world.character_creation.services import DraftIncompleteError, finalize_character
from world.character_sheets.models import CharacterSheet, Gender
from world.realms.models import Realm
from world.roster.models import Roster
from world.species.models import Species, SpeciesOrigin
from world.traits.models import CharacterTraitValue, Trait, TraitType


class CharacterFinalizationTests(TestCase):
    """Test character finalization with stats."""

    def setUp(self):
        """Set up test data."""
        from world.forms.models import Build, HeightBand

        self.account = AccountDB.objects.create(username="testuser")

        # Create starting area with realm
        self.realm = Realm.objects.create(
            name="Test Realm",
            description="Test realm",
        )
        self.area = StartingArea.objects.create(
            name="Test Area",
            description="Test area",
            realm=self.realm,
            access_level=StartingArea.AccessLevel.ALL,
        )

        # Get or create the 8 primary stats (may already exist from migration)
        self.stats = {}
        stat_names = [
            "strength",
            "agility",
            "stamina",
            "charm",
            "presence",
            "intellect",
            "wits",
            "willpower",
        ]
        for name in stat_names:
            trait, _created = Trait.objects.get_or_create(
                name=name,
                defaults={
                    "trait_type": TraitType.STAT,
                    "description": f"{name.capitalize()} stat",
                },
            )
            self.stats[name] = trait

        # Create roster
        self.roster = Roster.objects.create(name="Available Characters")

        # Create species and gender for complete drafts
        self.species = Species.objects.create(name="Human", description="Test species")
        self.gender, _ = Gender.objects.get_or_create(key="male", defaults={"display_name": "Male"})

        # Create species origin (permanent character data)
        self.species_origin = SpeciesOrigin.objects.create(
            species=self.species,
            name="Test Human",
            description="Test species origin",
        )

        # Create species option (CG mechanics - required for Heritage stage)
        self.species_option = SpeciesOption.objects.create(
            species_origin=self.species_origin,
            starting_area=self.area,
            cg_point_cost=0,
            trust_required=0,
            is_available=True,
        )

        # Create height band and build for appearance stage
        # Use unique height range outside all default bands (default bands end at 600)
        self.height_band = HeightBand.objects.create(
            name="service_test_band",
            display_name="Service Test Band",
            min_inches=700,
            max_inches=800,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        self.build = Build.objects.create(
            name="service_test_build",
            display_name="Service Test Build",
            weight_factor=Decimal("1.0"),
            is_cg_selectable=True,
        )

    def _create_complete_draft(self, stats, first_name="Test"):
        """Helper to create a complete draft for finalization testing."""
        return CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_species_option=self.species_option,
            selected_gender=self.gender,
            age=25,
            height_band=self.height_band,
            height_inches=750,
            build=self.build,
            draft_data={
                "first_name": first_name,
                "description": "A test character",
                "stats": stats,
                "lineage_is_orphan": True,  # Complete lineage stage
                "path_skills_complete": True,
                "traits_complete": True,
            },
        )

    def test_finalize_creates_character_trait_values(self):
        """Test that finalization creates CharacterTraitValue records."""
        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        )

        character = finalize_character(draft, add_to_roster=True)

        # Verify character was created
        assert character is not None
        assert character.db_key == "Test"

        # Verify trait values were created
        trait_values = CharacterTraitValue.objects.filter(character=character)
        assert trait_values.count() == 8

        # Verify specific values directly from database
        strength_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["strength"]
        )
        # Debug: print actual value if assertion fails
        if strength_value.value != 30:
            print(f"Expected strength=30, got {strength_value.value}")
            trait_values = CharacterTraitValue.objects.filter(character=character)
            all_values = [(v.trait.name, v.value) for v in trait_values]
            print(f"All values: {all_values}")
        assert strength_value.value == 30

        agility_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["agility"]
        )
        assert agility_value.value == 30

        willpower_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["willpower"]
        )
        assert willpower_value.value == 30

    def test_finalize_bulk_creates_trait_values(self):
        """Test that finalization uses bulk operations (no N+1)."""
        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            },
            first_name="Bulk Test",
        )

        # Count queries during finalization
        with CaptureQueriesContext(connection) as queries:
            finalize_character(draft, add_to_roster=True)

        # Check that we're not doing 8 individual creates
        # Should be: 1 fetch traits + 1 bulk_create
        # (Plus some queries for character/sheet creation)
        # This is a rough check - the key is we're NOT doing 16 queries
        # (8 trait lookups + 8 creates)
        create_queries = [
            q for q in queries if "INSERT" in q["sql"] and "traits_charactertraitvalue" in q["sql"]
        ]

        # Should be 1 bulk insert, not 8 individual inserts
        assert len(create_queries) == 1, f"Expected 1 bulk insert, got {len(create_queries)}"

    def test_finalize_rejects_incomplete_draft(self):
        """Test that finalization properly rejects incomplete drafts."""
        # Create a draft without stats (incomplete attributes stage)
        # Include appearance data to isolate the attributes stage test
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_species_option=self.species_option,
            selected_gender=self.gender,
            age=25,
            height_band=self.height_band,
            height_inches=750,
            build=self.build,
            draft_data={
                "first_name": "Incomplete",
                "lineage_is_orphan": True,  # Complete heritage/lineage
                "path_skills_complete": True,
                "traits_complete": True,
                # No stats field - attributes stage incomplete
            },
        )

        # Should raise DraftIncompleteError
        with self.assertRaises(DraftIncompleteError) as cm:
            finalize_character(draft, add_to_roster=True)

        assert "Attributes" in str(cm.exception)

    def test_finalize_creates_character_sheet(self):
        """Test that finalization creates CharacterSheet with stats."""
        draft = self._create_complete_draft(
            stats={
                "strength": 30,  # 3 points
                "agility": 30,  # 3 points
                "stamina": 30,  # 3 points
                "charm": 20,  # 2 points
                "presence": 20,  # 2 points
                "intellect": 20,  # 2 points
                "wits": 30,  # 3 points
                "willpower": 30,  # 3 points
            },
            first_name="Sheet Test",
        )

        character = finalize_character(draft, add_to_roster=True)

        # Verify character sheet exists
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet is not None

        # Verify stats were created with correct values
        strength_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["strength"]
        )
        assert strength_value.value == 30

        willpower_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["willpower"]
        )
        assert willpower_value.value == 30

    def test_finalize_populates_physical_stats(self):
        """Test that finalization populates height, build, and weight on CharacterSheet."""
        from world.forms.models import Build, HeightBand

        # Create height band and build for physical stats directly to avoid factory issues
        # Use unique height range outside all default bands (default bands end at 600)
        height_band = HeightBand.objects.create(
            name="finalize_test_band",
            display_name="Finalize Test Band",
            min_inches=700,
            max_inches=800,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        build = Build.objects.create(
            name="finalize_test_build",
            display_name="Finalize Test Build",
            weight_factor=Decimal("1.0"),  # Simple factor for easy verification
            is_cg_selectable=True,
        )

        # Create a complete draft with physical stats
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_species_option=self.species_option,
            selected_gender=self.gender,
            age=25,
            height_band=height_band,
            height_inches=750,  # Use height within unique band (700-800)
            build=build,
            draft_data={
                "first_name": "Physical",
                "description": "A test character with physical stats",
                "stats": {
                    "strength": 30,
                    "agility": 30,
                    "stamina": 30,
                    "charm": 20,
                    "presence": 20,
                    "intellect": 20,
                    "wits": 30,
                    "willpower": 30,
                },
                "lineage_is_orphan": True,
                "path_skills_complete": True,
                "traits_complete": True,
            },
        )

        character = finalize_character(draft, add_to_roster=True)

        # Verify character sheet has physical stats populated
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.true_height_inches == 750
        assert sheet.build == build
        # Weight calculated as height_inches * weight_factor = 750 * 1.0 = 750
        assert sheet.weight_pounds == 750
