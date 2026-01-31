"""
Tests for character creation services.
"""

from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from evennia.accounts.models import AccountDB

from world.character_creation.models import Beginnings, CharacterDraft, StartingArea
from world.character_creation.services import DraftIncompleteError, finalize_character
from world.character_sheets.models import CharacterSheet, Gender
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.realms.models import Realm
from world.roster.models import Roster
from world.species.models import Species
from world.traits.models import CharacterTraitValue, Trait, TraitType


class CharacterFinalizationTests(TestCase):
    """Test character finalization with stats."""

    def setUp(self):
        """Set up test data."""
        from world.forms.models import Build, HeightBand

        # Flush SharedMemoryModel caches to prevent test pollution
        # CharacterTraitValue uses SharedMemoryModel which caches instances in memory.
        # When tests run with transaction rollback, the cache persists stale data.
        CharacterTraitValue.flush_instance_cache()
        Trait.flush_instance_cache()

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

        # Get or create the 9 primary stats (may already exist from migration)
        self.stats = {}
        stat_names = [
            "strength",
            "agility",
            "stamina",
            "charm",
            "presence",
            "perception",
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

        # Create beginnings (worldbuilding path for CG)
        self.beginnings = Beginnings.objects.create(
            name="Test Commoner",
            description="Test commoner background",
            starting_area=self.area,
            trust_required=0,
            is_active=True,
            family_known=False,  # Skip family requirement
        )
        self.beginnings.allowed_species.add(self.species)

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

        # Create path for stage 5 completion
        self.path = PathFactory(
            name="Service Test Path",
            stage=PathStage.PROSPECT,
            minimum_level=1,
        )

    def _create_complete_draft(self, stats, first_name="Test"):
        """Helper to create a complete draft for finalization testing."""
        return CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
            age=25,
            height_band=self.height_band,
            height_inches=750,
            build=self.build,
            draft_data={
                "first_name": first_name,
                "description": "A test character",
                "stats": stats,
                "lineage_is_orphan": True,  # Complete lineage stage
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
                "perception": 20,
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
        assert trait_values.count() == 9

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
                "perception": 20,
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
            selected_beginnings=self.beginnings,
            selected_species=self.species,
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
                "perception": 20,  # 2 points
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
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
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
                    "perception": 20,
                    "intellect": 20,
                    "wits": 30,
                    "willpower": 30,
                },
                "lineage_is_orphan": True,
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


class FinalizeCharacterSkillsTests(TestCase):
    """Tests for skill creation during character finalization."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for skill finalization tests."""
        from decimal import Decimal

        from world.character_sheets.models import Gender
        from world.forms.models import Build, HeightBand
        from world.realms.models import Realm
        from world.skills.factories import SkillFactory, SpecializationFactory
        from world.skills.models import CharacterSkillValue, CharacterSpecializationValue
        from world.species.models import Species
        from world.traits.models import Trait, TraitCategory, TraitType

        # Flush SharedMemoryModel caches to prevent test pollution
        CharacterSkillValue.flush_instance_cache()
        CharacterSpecializationValue.flush_instance_cache()
        Trait.flush_instance_cache()

        # Create basic CG requirements
        cls.realm = Realm.objects.create(
            name="Skill Test Realm",
            description="Test realm for skill tests",
        )
        cls.area = StartingArea.objects.create(
            name="Skill Test Area",
            description="Test area for skill tests",
            realm=cls.realm,
            access_level=StartingArea.AccessLevel.ALL,
        )
        cls.species = Species.objects.create(
            name="Skill Test Species",
            description="Test species for skill tests",
        )
        cls.gender, _ = Gender.objects.get_or_create(
            key="skill_test_gender",
            defaults={"display_name": "Skill Test Gender"},
        )

        # Create beginnings
        cls.beginnings = Beginnings.objects.create(
            name="Skill Test Beginnings",
            description="Test beginnings for skill tests",
            starting_area=cls.area,
            trust_required=0,
            is_active=True,
            family_known=False,
        )
        cls.beginnings.allowed_species.add(cls.species)

        # Create height band and build for appearance stage
        cls.height_band = HeightBand.objects.create(
            name="skill_test_band",
            display_name="Skill Test Band",
            min_inches=900,
            max_inches=1000,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        cls.build = Build.objects.create(
            name="skill_test_build",
            display_name="Skill Test Build",
            weight_factor=Decimal("1.0"),
            is_cg_selectable=True,
        )

        # Create stats
        for stat_name in [
            "strength",
            "agility",
            "stamina",
            "charm",
            "presence",
            "perception",
            "intellect",
            "wits",
            "willpower",
        ]:
            Trait.objects.get_or_create(
                name=stat_name,
                defaults={
                    "trait_type": TraitType.STAT,
                    "category": TraitCategory.PHYSICAL
                    if stat_name in ["strength", "agility", "stamina"]
                    else TraitCategory.SOCIAL,
                },
            )

        # Create skills with specific names
        cls.melee_skill = SkillFactory(trait__name="Melee Combat")
        cls.defense_skill = SkillFactory(trait__name="Defense")
        cls.swords_spec = SpecializationFactory(name="Swords", parent_skill=cls.melee_skill)

        # Create path for stage 5 completion
        cls.path = PathFactory(
            name="Skill Finalize Test Path",
            stage=PathStage.PROSPECT,
            minimum_level=1,
        )

    def setUp(self):
        """Set up per-test data."""
        from world.skills.models import CharacterSkillValue, CharacterSpecializationValue
        from world.traits.models import CharacterTraitValue, Trait

        # Flush caches before each test
        CharacterSkillValue.flush_instance_cache()
        CharacterSpecializationValue.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        Trait.flush_instance_cache()

        self.account = AccountDB.objects.create(username=f"skilltest_{id(self)}")

    def _create_complete_draft(self):
        """Create a draft ready for finalization."""
        return CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
            age=25,
            height_band=self.height_band,
            height_inches=950,
            build=self.build,
            draft_data={
                "first_name": "SkillTest",
                "stats": {
                    "strength": 30,
                    "agility": 30,
                    "stamina": 30,
                    "charm": 20,
                    "presence": 20,
                    "perception": 20,
                    "intellect": 20,
                    "wits": 30,
                    "willpower": 30,
                },
                "skills": {},
                "specializations": {},
                "lineage_is_orphan": True,
                "traits_complete": True,
            },
        )

    def test_finalize_creates_skill_values(self):
        """Finalization should create CharacterSkillValue records."""
        from world.skills.models import CharacterSkillValue

        draft = self._create_complete_draft()
        draft.draft_data["skills"] = {str(self.melee_skill.pk): 30}
        draft.draft_data["specializations"] = {}
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        skill_value = CharacterSkillValue.objects.get(
            character=character,
            skill=self.melee_skill,
        )
        assert skill_value.value == 30
        assert skill_value.development_points == 0
        assert skill_value.rust_points == 0

    def test_finalize_creates_specialization_values(self):
        """Finalization should create CharacterSpecializationValue records."""
        from world.skills.models import CharacterSpecializationValue

        draft = self._create_complete_draft()
        draft.draft_data["skills"] = {str(self.melee_skill.pk): 30}
        draft.draft_data["specializations"] = {str(self.swords_spec.pk): 20}
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        spec_value = CharacterSpecializationValue.objects.get(
            character=character,
            specialization=self.swords_spec,
        )
        assert spec_value.value == 20
        assert spec_value.development_points == 0

    def test_finalize_skips_zero_value_skills(self):
        """Skills with value 0 should not create records."""
        from world.skills.models import CharacterSkillValue

        draft = self._create_complete_draft()
        draft.draft_data["skills"] = {str(self.melee_skill.pk): 0}
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        assert not CharacterSkillValue.objects.filter(
            character=character,
            skill=self.melee_skill,
        ).exists()


class FinalizeCharacterPathHistoryTests(TestCase):
    """Tests for path history creation during character finalization."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for path history tests."""
        from decimal import Decimal

        from world.character_sheets.models import Gender
        from world.forms.models import Build, HeightBand
        from world.realms.models import Realm
        from world.species.models import Species
        from world.traits.models import Trait, TraitCategory, TraitType

        # Create basic CG requirements
        cls.realm = Realm.objects.create(
            name="Path History Test Realm",
            description="Test realm for path history tests",
        )
        cls.area = StartingArea.objects.create(
            name="Path History Test Area",
            description="Test area for path history tests",
            realm=cls.realm,
            access_level=StartingArea.AccessLevel.ALL,
        )
        cls.species = Species.objects.create(
            name="Path History Test Species",
            description="Test species for path history tests",
        )
        cls.gender, _ = Gender.objects.get_or_create(
            key="path_history_test_gender",
            defaults={"display_name": "Path History Test Gender"},
        )

        # Create beginnings
        cls.beginnings = Beginnings.objects.create(
            name="Path History Test Beginnings",
            description="Test beginnings for path history tests",
            starting_area=cls.area,
            trust_required=0,
            is_active=True,
            family_known=False,
        )
        cls.beginnings.allowed_species.add(cls.species)

        # Create height band and build for appearance stage
        cls.height_band = HeightBand.objects.create(
            name="path_history_test_band",
            display_name="Path History Test Band",
            min_inches=1100,
            max_inches=1200,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        cls.build = Build.objects.create(
            name="path_history_test_build",
            display_name="Path History Test Build",
            weight_factor=Decimal("1.0"),
            is_cg_selectable=True,
        )

        # Create stats
        for stat_name in [
            "strength",
            "agility",
            "stamina",
            "charm",
            "presence",
            "perception",
            "intellect",
            "wits",
            "willpower",
        ]:
            Trait.objects.get_or_create(
                name=stat_name,
                defaults={
                    "trait_type": TraitType.STAT,
                    "category": TraitCategory.PHYSICAL
                    if stat_name in ["strength", "agility", "stamina"]
                    else TraitCategory.SOCIAL,
                },
            )

        # Create path for testing
        cls.path = PathFactory(
            name="Path History Test Path",
            stage=PathStage.PROSPECT,
            minimum_level=1,
        )

    def setUp(self):
        """Set up per-test data."""
        from world.traits.models import CharacterTraitValue, Trait

        # Flush caches before each test
        CharacterTraitValue.flush_instance_cache()
        Trait.flush_instance_cache()

        self.account = AccountDB.objects.create(username=f"pathhistorytest_{id(self)}")

    def _create_complete_draft(self):
        """Create a draft ready for finalization."""
        return CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
            age=25,
            height_band=self.height_band,
            height_inches=1150,
            build=self.build,
            draft_data={
                "first_name": "PathHistoryTest",
                "stats": {
                    "strength": 30,
                    "agility": 30,
                    "stamina": 30,
                    "charm": 20,
                    "presence": 20,
                    "perception": 20,
                    "intellect": 20,
                    "wits": 30,
                    "willpower": 30,
                },
                "skills": {},
                "specializations": {},
                "lineage_is_orphan": True,
                "traits_complete": True,
            },
        )

    def test_creates_path_history_on_finalize(self):
        """finalize_character creates CharacterPathHistory record."""
        from world.progression.models import CharacterPathHistory

        draft = self._create_complete_draft()

        character = finalize_character(draft, add_to_roster=True)

        history = CharacterPathHistory.objects.filter(character=character).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.path, self.path)


class FinalizeCharacterGoalsTests(TestCase):
    """Tests for goal creation during character finalization."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for goal finalization tests."""
        from decimal import Decimal

        from world.character_sheets.models import Gender
        from world.forms.models import Build, HeightBand
        from world.mechanics.models import ModifierCategory, ModifierType
        from world.realms.models import Realm
        from world.species.models import Species
        from world.traits.models import Trait, TraitCategory, TraitType

        # Flush SharedMemoryModel caches to prevent test pollution
        Trait.flush_instance_cache()

        # Get or create goal category and domains
        cls.goal_cat, _ = ModifierCategory.objects.get_or_create(name="goal")
        cls.standing, _ = ModifierType.objects.get_or_create(name="Standing", category=cls.goal_cat)
        cls.drives, _ = ModifierType.objects.get_or_create(name="Drives", category=cls.goal_cat)

        # Create basic CG requirements
        cls.realm = Realm.objects.create(
            name="Goals Test Realm",
            description="Test realm for goal tests",
        )
        cls.area = StartingArea.objects.create(
            name="Goals Test Area",
            description="Test area for goal tests",
            realm=cls.realm,
            access_level=StartingArea.AccessLevel.ALL,
        )
        cls.species = Species.objects.create(
            name="Goals Test Species",
            description="Test species for goal tests",
        )
        cls.gender, _ = Gender.objects.get_or_create(
            key="goals_test_gender",
            defaults={"display_name": "Goals Test Gender"},
        )

        # Create beginnings
        cls.beginnings = Beginnings.objects.create(
            name="Goals Test Beginnings",
            description="Test beginnings for goal tests",
            starting_area=cls.area,
            trust_required=0,
            is_active=True,
            family_known=False,
        )
        cls.beginnings.allowed_species.add(cls.species)

        # Create height band and build for appearance stage
        cls.height_band = HeightBand.objects.create(
            name="goals_test_band",
            display_name="Goals Test Band",
            min_inches=1300,
            max_inches=1400,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        cls.build = Build.objects.create(
            name="goals_test_build",
            display_name="Goals Test Build",
            weight_factor=Decimal("1.0"),
            is_cg_selectable=True,
        )

        # Create stats
        for stat_name in [
            "strength",
            "agility",
            "stamina",
            "charm",
            "presence",
            "perception",
            "intellect",
            "wits",
            "willpower",
        ]:
            Trait.objects.get_or_create(
                name=stat_name,
                defaults={
                    "trait_type": TraitType.STAT,
                    "category": TraitCategory.PHYSICAL
                    if stat_name in ["strength", "agility", "stamina"]
                    else TraitCategory.SOCIAL,
                },
            )

        # Create path for testing
        cls.path = PathFactory(
            name="Goals Test Path",
            stage=PathStage.PROSPECT,
            minimum_level=1,
        )

    def setUp(self):
        """Set up per-test data."""
        from world.traits.models import CharacterTraitValue, Trait

        # Flush caches before each test
        CharacterTraitValue.flush_instance_cache()
        Trait.flush_instance_cache()

        self.account = AccountDB.objects.create(username=f"goalstest_{id(self)}")

    def _create_complete_draft(self):
        """Create a draft ready for finalization."""
        return CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
            age=25,
            height_band=self.height_band,
            height_inches=1350,
            build=self.build,
            draft_data={
                "first_name": "GoalsTest",
                "stats": {
                    "strength": 30,
                    "agility": 30,
                    "stamina": 30,
                    "charm": 20,
                    "presence": 20,
                    "perception": 20,
                    "intellect": 20,
                    "wits": 30,
                    "willpower": 30,
                },
                "skills": {},
                "specializations": {},
                "lineage_is_orphan": True,
                "traits_complete": True,
            },
        )

    def test_creates_goals_from_draft_data(self):
        """Goals in draft_data are created as CharacterGoal records."""
        from world.goals.models import CharacterGoal

        draft = self._create_complete_draft()

        # Add goals to draft_data
        draft.draft_data["goals"] = [
            {"domain": "standing", "text": "Become a knight", "points": 15},
            {"domain": "drives", "text": "Avenge my mentor", "points": 10},
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        goals = CharacterGoal.objects.filter(character=character)
        assert goals.count() == 2

        standing_goal = goals.get(domain=self.standing)
        assert standing_goal.points == 15
        assert standing_goal.notes == "Become a knight"

        drives_goal = goals.get(domain=self.drives)
        assert drives_goal.points == 10
        assert drives_goal.notes == "Avenge my mentor"

    def test_no_goals_created_when_draft_has_none(self):
        """No goals created if draft_data has no goals."""
        from world.goals.models import CharacterGoal

        draft = self._create_complete_draft()
        draft.draft_data.pop("goals", None)
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        goals = CharacterGoal.objects.filter(character=character)
        assert goals.count() == 0

    def test_skips_invalid_goal_domains(self):
        """Invalid goal domains are skipped with a warning."""
        from world.goals.models import CharacterGoal

        draft = self._create_complete_draft()

        # Add a goal with an invalid domain
        draft.draft_data["goals"] = [
            {"domain": "standing", "text": "Valid goal", "points": 15},
            {"domain": "nonexistent_domain", "text": "Invalid goal", "points": 10},
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        goals = CharacterGoal.objects.filter(character=character)
        # Only the valid goal should be created
        assert goals.count() == 1
        assert goals.first().domain == self.standing

    def test_skips_zero_point_goals(self):
        """Goals with 0 points are skipped."""
        from world.goals.models import CharacterGoal

        draft = self._create_complete_draft()

        draft.draft_data["goals"] = [
            {"domain": "standing", "text": "Valid goal", "points": 15},
            {"domain": "drives", "text": "Zero point goal", "points": 0},
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        goals = CharacterGoal.objects.filter(character=character)
        assert goals.count() == 1
        assert goals.first().domain == self.standing
