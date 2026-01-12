"""
Tests for character creation system.

Tests models, validation, serializers, and finalization functionality.
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from evennia.accounts.models import AccountDB

from world.character_creation.models import (
    STAT_FREE_POINTS,
    CharacterDraft,
    StartingArea,
)
from world.character_creation.serializers import CharacterDraftSerializer
from world.character_creation.services import DraftIncompleteError, finalize_character
from world.character_sheets.models import CharacterSheet, Gender, Species
from world.realms.models import Realm
from world.roster.models import Roster
from world.traits.models import CharacterTraitValue, Trait, TraitType


class CharacterDraftStatsValidationTests(TestCase):
    """Test stat validation in CharacterDraft model."""

    def setUp(self):
        """Set up test data."""
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

        self.draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
        )

        # Get or create the 8 primary stats (may already exist from migration)
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
            Trait.objects.get_or_create(
                name=name,
                defaults={
                    "trait_type": TraitType.STAT,
                    "description": f"{name.capitalize()} stat",
                },
            )

    def test_calculate_stats_free_points_no_stats(self):
        """Test free points calculation with no stats set."""
        free_points = self.draft._calculate_stats_free_points()
        assert free_points == STAT_FREE_POINTS

    def test_calculate_stats_free_points_default_stats(self):
        """Test free points with all stats at default value (20)."""
        self.draft.draft_data = {
            "stats": {
                "strength": 20,
                "agility": 20,
                "stamina": 20,
                "charm": 20,
                "presence": 20,
                "intellect": 20,
                "wits": 20,
                "willpower": 20,
            }
        }
        self.draft.save()

        free_points = self.draft._calculate_stats_free_points()
        # 8 stats * 2 = 16 points spent, 21 - 16 = 5 free
        assert free_points == STAT_FREE_POINTS

    def test_calculate_stats_free_points_all_spent(self):
        """Test free points when all points are spent."""
        self.draft.draft_data = {
            "stats": {
                "strength": 30,  # 3 points
                "agility": 30,  # 3 points
                "stamina": 30,  # 3 points
                "charm": 20,  # 2 points
                "presence": 20,  # 2 points
                "intellect": 20,  # 2 points
                "wits": 30,  # 3 points
                "willpower": 30,  # 3 points
            }
        }
        self.draft.save()

        free_points = self.draft._calculate_stats_free_points()
        # 21 points spent (3+3+3+2+2+2+3+3), 21 - 21 = 0
        assert free_points == 0

    def test_calculate_stats_free_points_over_budget(self):
        """Test free points when over budget (negative)."""
        self.draft.draft_data = {
            "stats": {
                "strength": 50,  # 5 points
                "agility": 50,  # 5 points
                "stamina": 40,  # 4 points
                "charm": 20,  # 2 points
                "presence": 20,  # 2 points
                "intellect": 20,  # 2 points
                "wits": 20,  # 2 points
                "willpower": 20,  # 2 points
            }
        }
        self.draft.save()

        free_points = self.draft._calculate_stats_free_points()
        # 24 points spent (5+5+4+2+2+2+2+2), 21 - 24 = -3
        assert free_points == -3

    def test_is_attributes_complete_missing_stats(self):
        """Test validation fails with missing stats."""
        self.draft.draft_data = {
            "stats": {
                "strength": 20,
                "agility": 20,
                # Missing 6 stats
            }
        }
        self.draft.save()

        assert not self.draft._is_attributes_complete()

    def test_is_attributes_complete_non_integer_value(self):
        """Test validation fails with non-integer values."""
        self.draft.draft_data = {
            "stats": {
                "strength": 20.5,  # Float instead of int
                "agility": 20,
                "stamina": 20,
                "charm": 20,
                "presence": 20,
                "intellect": 20,
                "wits": 20,
                "willpower": 20,
            }
        }
        self.draft.save()

        assert not self.draft._is_attributes_complete()

    def test_is_attributes_complete_not_multiple_of_10(self):
        """Test validation fails with values not multiple of 10."""
        self.draft.draft_data = {
            "stats": {
                "strength": 25,  # Not a multiple of 10
                "agility": 20,
                "stamina": 20,
                "charm": 20,
                "presence": 20,
                "intellect": 20,
                "wits": 20,
                "willpower": 20,
            }
        }
        self.draft.save()

        assert not self.draft._is_attributes_complete()

    def test_is_attributes_complete_out_of_range(self):
        """Test validation fails with values out of range."""
        # Test below minimum
        self.draft.draft_data = {
            "stats": {
                "strength": 5,  # Below minimum (10)
                "agility": 20,
                "stamina": 20,
                "charm": 20,
                "presence": 20,
                "intellect": 20,
                "wits": 20,
                "willpower": 20,
            }
        }
        self.draft.save()

        assert not self.draft._is_attributes_complete()

        # Test above maximum
        self.draft.draft_data = {
            "stats": {
                "strength": 60,  # Above maximum (50)
                "agility": 20,
                "stamina": 20,
                "charm": 20,
                "presence": 20,
                "intellect": 20,
                "wits": 20,
                "willpower": 20,
            }
        }
        self.draft.save()

        assert not self.draft._is_attributes_complete()

    def test_is_attributes_complete_free_points_not_zero(self):
        """Test validation fails when free points != 0."""
        self.draft.draft_data = {
            "stats": {
                "strength": 20,
                "agility": 20,
                "stamina": 20,
                "charm": 20,
                "presence": 20,
                "intellect": 20,
                "wits": 20,
                "willpower": 20,
            }
        }
        self.draft.save()

        # With all stats at 20, free points = 5 (not 0)
        assert not self.draft._is_attributes_complete()

    def test_is_attributes_complete_valid(self):
        """Test validation passes with valid stats."""
        self.draft.draft_data = {
            "stats": {
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        }
        self.draft.save()

        # 21 points spent exactly, all valid
        assert self.draft._is_attributes_complete()

    def test_stage_completion_includes_attributes(self):
        """Test that stage_completion includes attributes stage."""
        self.draft.draft_data = {
            "stats": {
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        }
        self.draft.save()

        stage_completion = self.draft.get_stage_completion()
        assert CharacterDraft.Stage.ATTRIBUTES in stage_completion
        assert stage_completion[CharacterDraft.Stage.ATTRIBUTES] is True


class CharacterDraftSerializerValidationTests(TestCase):
    """Test stat validation in CharacterDraftSerializer."""

    def setUp(self):
        """Set up test data."""
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

        self.draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
        )

    def test_validate_draft_data_invalid_stat_name(self):
        """Test validation fails with invalid stat name."""
        data = {
            "draft_data": {
                "stats": {
                    "invalid_stat": 20,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert not serializer.is_valid()
        assert "draft_data" in serializer.errors

    def test_validate_draft_data_non_integer_value(self):
        """Test validation fails with non-integer stat value."""
        data = {
            "draft_data": {
                "stats": {
                    "strength": 20.5,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert not serializer.is_valid()
        assert "draft_data" in serializer.errors

    def test_validate_draft_data_not_multiple_of_10(self):
        """Test validation fails when stat not multiple of 10."""
        data = {
            "draft_data": {
                "stats": {
                    "strength": 25,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert not serializer.is_valid()
        assert "draft_data" in serializer.errors

    def test_validate_draft_data_out_of_range(self):
        """Test validation fails with out of range values."""
        # Below minimum
        data = {
            "draft_data": {
                "stats": {
                    "strength": 5,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert not serializer.is_valid()
        assert "draft_data" in serializer.errors

        # Above maximum
        data = {
            "draft_data": {
                "stats": {
                    "strength": 60,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert not serializer.is_valid()
        assert "draft_data" in serializer.errors

    def test_validate_draft_data_valid_stats(self):
        """Test validation passes with valid stats."""
        data = {
            "draft_data": {
                "stats": {
                    "strength": 30,
                    "agility": 20,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert serializer.is_valid(), serializer.errors


class CharacterFinalizationTests(TestCase):
    """Test character finalization with stats."""

    def setUp(self):
        """Set up test data."""
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

    def _create_complete_draft(self, stats, first_name="Test"):
        """Helper to create a complete draft for finalization testing."""
        return CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_species=self.species,
            selected_gender=self.gender,
            age=25,
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
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_species=self.species,
            selected_gender=self.gender,
            age=25,
            draft_data={
                "first_name": "Incomplete",
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
