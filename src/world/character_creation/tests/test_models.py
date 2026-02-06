"""
Tests for character creation models.
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    StartingAreaFactory,
)
from world.character_creation.models import (
    STAT_FREE_POINTS,
    CharacterDraft,
    StartingArea,
)
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.forms.factories import BuildFactory, HeightBandFactory
from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory
from world.realms.models import Realm
from world.species.factories import SpeciesFactory
from world.traits.models import Trait, TraitType


class AppearanceStageCompletionTest(TestCase):
    """Test appearance stage completion logic."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.height_band = HeightBandFactory(
            name="test_average", min_inches=68, max_inches=71, is_cg_selectable=True
        )
        cls.build = BuildFactory(name="test_athletic", is_cg_selectable=True)

    def test_appearance_incomplete_without_all_fields(self):
        """Test appearance is incomplete when missing required fields."""
        draft = CharacterDraftFactory(account=self.account)
        completion = draft.get_stage_completion()
        self.assertFalse(completion[CharacterDraft.Stage.APPEARANCE])

    def test_appearance_incomplete_without_age(self):
        """Test appearance is incomplete when age is missing."""
        draft = CharacterDraftFactory(
            account=self.account,
            age=None,
            height_band=self.height_band,
            height_inches=70,
            build=self.build,
        )
        completion = draft.get_stage_completion()
        self.assertFalse(completion[CharacterDraft.Stage.APPEARANCE])

    def test_appearance_incomplete_without_height_band(self):
        """Test appearance is incomplete when height_band is missing."""
        draft = CharacterDraftFactory(
            account=self.account,
            age=25,
            height_band=None,
            height_inches=70,
            build=self.build,
        )
        completion = draft.get_stage_completion()
        self.assertFalse(completion[CharacterDraft.Stage.APPEARANCE])

    def test_appearance_incomplete_without_height_inches(self):
        """Test appearance is incomplete when height_inches is missing."""
        draft = CharacterDraftFactory(
            account=self.account,
            age=25,
            height_band=self.height_band,
            height_inches=None,
            build=self.build,
        )
        completion = draft.get_stage_completion()
        self.assertFalse(completion[CharacterDraft.Stage.APPEARANCE])

    def test_appearance_incomplete_without_build(self):
        """Test appearance is incomplete when build is missing."""
        draft = CharacterDraftFactory(
            account=self.account,
            age=25,
            height_band=self.height_band,
            height_inches=70,
            build=None,
        )
        completion = draft.get_stage_completion()
        self.assertFalse(completion[CharacterDraft.Stage.APPEARANCE])

    def test_appearance_complete_with_all_fields(self):
        """Test appearance is complete when all fields are set."""
        draft = CharacterDraftFactory(
            account=self.account,
            age=25,
            height_band=self.height_band,
            height_inches=70,
            build=self.build,
        )
        completion = draft.get_stage_completion()
        self.assertTrue(completion[CharacterDraft.Stage.APPEARANCE])


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

        # Get or create the 9 primary stats (may already exist from migration)
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
                "perception": 20,
                "intellect": 20,
                "wits": 20,
                "willpower": 20,
            }
        }
        self.draft.save()

        free_points = self.draft._calculate_stats_free_points()
        # 9 stats * 2 = 18 points spent, 23 - 18 = 5 free
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
                "perception": 20,  # 2 points
                "intellect": 20,  # 2 points
                "wits": 30,  # 3 points
                "willpower": 30,  # 3 points
            }
        }
        self.draft.save()

        free_points = self.draft._calculate_stats_free_points()
        # 23 points spent (3+3+3+2+2+2+2+3+3), 23 - 23 = 0
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
                "perception": 20,  # 2 points
                "intellect": 20,  # 2 points
                "wits": 20,  # 2 points
                "willpower": 20,  # 2 points
            }
        }
        self.draft.save()

        free_points = self.draft._calculate_stats_free_points()
        # 26 points spent (5+5+4+2+2+2+2+2+2), 23 - 26 = -3
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
                "perception": 20,
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
                "perception": 20,
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
                "perception": 20,
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
                "perception": 20,
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
                "perception": 20,
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
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        }
        self.draft.save()

        # 23 points spent exactly, all valid
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
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        }
        self.draft.save()

        stage_completion = self.draft.get_stage_completion()
        assert CharacterDraft.Stage.ATTRIBUTES in stage_completion
        assert stage_completion[CharacterDraft.Stage.ATTRIBUTES] is True


class BeginningsModelTests(TestCase):
    """Test Beginnings model."""

    @classmethod
    def setUpTestData(cls):
        cls.area = StartingAreaFactory(name="Test Area")
        cls.species = SpeciesFactory(name="TestSpecies")

    def test_beginnings_creation(self):
        """Test basic Beginnings model creation."""
        beginnings = BeginningsFactory(
            name="Normal Upbringing",
            description="Raised in the city with conventional background.",
            starting_area=self.area,
        )
        assert beginnings.name == "Normal Upbringing"
        assert beginnings.starting_area == self.area
        assert beginnings.trust_required == 0
        assert beginnings.is_active is True
        assert beginnings.family_known is True
        assert beginnings.grants_species_languages is True
        assert beginnings.social_rank == 0
        assert beginnings.cg_point_cost == 0

    def test_beginnings_allowed_species_m2m(self):
        """Test Beginnings can have M2M to Species."""
        beginnings = BeginningsFactory(starting_area=self.area)
        beginnings.allowed_species.add(self.species)
        assert self.species in beginnings.allowed_species.all()

    def test_beginnings_grants_species_languages_flag(self):
        """Test grants_species_languages flag for Misbegotten types."""
        beginnings = BeginningsFactory(
            starting_area=self.area,
            grants_species_languages=False,
            family_known=False,
        )
        assert beginnings.grants_species_languages is False
        assert beginnings.family_known is False

    def test_is_accessible_by_inactive_returns_false(self):
        """Inactive beginnings are not accessible to anyone."""
        beginnings = BeginningsFactory(starting_area=self.area, is_active=False)
        account = AccountFactory()
        assert beginnings.is_accessible_by(account) is False

    def test_is_accessible_by_staff_always_true(self):
        """Staff can access all active beginnings."""
        beginnings = BeginningsFactory(starting_area=self.area, trust_required=10)
        account = AccountFactory(is_staff=True)
        assert beginnings.is_accessible_by(account) is True

    def test_is_accessible_by_no_trust_required(self):
        """Anyone can access beginnings with trust_required=0."""
        beginnings = BeginningsFactory(starting_area=self.area, trust_required=0)
        account = AccountFactory()
        assert beginnings.is_accessible_by(account) is True

    def test_is_accessible_by_trust_required_no_trust_attr(self):
        """Account without trust attribute cannot access trust-gated options."""
        beginnings = BeginningsFactory(starting_area=self.area, trust_required=5)
        account = AccountFactory()
        # Account has no .trust attribute, so should be denied
        assert beginnings.is_accessible_by(account) is False

    def test_is_accessible_by_sufficient_trust(self):
        """Account with sufficient trust can access trust-gated options."""
        beginnings = BeginningsFactory(starting_area=self.area, trust_required=5)
        account = AccountFactory()
        account.trust = 10  # Mock trust attribute
        assert beginnings.is_accessible_by(account) is True

    def test_is_accessible_by_insufficient_trust(self):
        """Account with insufficient trust cannot access trust-gated options."""
        beginnings = BeginningsFactory(starting_area=self.area, trust_required=10)
        account = AccountFactory()
        account.trust = 5  # Mock trust attribute (below required)
        assert beginnings.is_accessible_by(account) is False

    def test_str_representation(self):
        """Test __str__ returns name and area."""
        beginnings = BeginningsFactory(
            name="Noble Birth",
            starting_area=self.area,
        )
        assert str(beginnings) == "Noble Birth (Test Area)"


class CharacterDraftBeginningsTests(TestCase):
    """Test CharacterDraft with Beginnings integration."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.area = StartingAreaFactory()

    def test_draft_selected_beginnings_fk(self):
        """Test CharacterDraft can reference Beginnings."""
        beginnings = BeginningsFactory(starting_area=self.area)
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=beginnings,
        )
        assert draft.selected_beginnings == beginnings

    def test_draft_beginnings_nullable(self):
        """Test selected_beginnings can be null."""
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
        )
        assert draft.selected_beginnings is None


class PathSkillsStageCompletionTest(TestCase):
    """Test path & skills stage completion logic."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.path = PathFactory(
            name="Path of Steel",
            stage=PathStage.PROSPECT,
            minimum_level=1,
        )

    def test_path_skills_incomplete_without_path(self):
        """Stage 5 is incomplete without path selection."""
        draft = CharacterDraftFactory(account=self.account, selected_path=None)
        completion = draft.get_stage_completion()
        self.assertFalse(completion[CharacterDraft.Stage.PATH_SKILLS])

    def test_path_skills_complete_with_path_and_valid_skills(self):
        """Stage 5 is complete with path and valid skill allocation."""
        draft = CharacterDraftFactory(
            account=self.account,
            selected_path=self.path,
            draft_data={"skills": {}, "specializations": {}},
        )
        # With empty skills but path selected, stage is complete
        # (validation passes because total spent <= budget)
        completion = draft.get_stage_completion()
        self.assertTrue(completion[CharacterDraft.Stage.PATH_SKILLS])


class StatCapEnforcementTests(TestCase):
    """Test stat cap enforcement when distinctions provide stat bonuses."""

    @classmethod
    def setUpTestData(cls):
        cls.stat_category = ModifierCategoryFactory(name="stat")
        cls.strength_type = ModifierTypeFactory(name="strength", category=cls.stat_category)
        cls.agility_type = ModifierTypeFactory(name="agility", category=cls.stat_category)

    def _create_draft_with_stats(self, stats):
        """Create a draft with the given stat allocation."""
        draft = CharacterDraftFactory()
        draft.draft_data["stats"] = stats
        draft.save(update_fields=["draft_data"])
        return draft

    def _add_distinction_to_draft(self, draft, distinction):
        """Add a distinction to draft's JSON data."""
        distinctions = draft.draft_data.get("distinctions", [])
        distinctions.append(
            {
                "distinction_id": distinction.id,
                "distinction_name": distinction.name,
                "distinction_slug": distinction.slug,
                "category_slug": distinction.category.slug,
                "rank": 1,
                "cost": distinction.cost_per_rank,
                "notes": "",
            }
        )
        draft.draft_data["distinctions"] = distinctions
        draft.save(update_fields=["draft_data"])

    def test_get_stat_bonuses_from_distinctions_empty(self):
        """No distinctions means no bonuses."""
        draft = CharacterDraftFactory()
        bonuses = draft.get_stat_bonuses_from_distinctions()
        assert bonuses == {}

    def test_get_stat_bonuses_from_distinctions_with_effect(self):
        """Distinction with stat effect returns bonus in display scale."""
        distinction = DistinctionFactory()
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.strength_type,
            value_per_rank=10,
            description="",
        )
        draft = CharacterDraftFactory()
        self._add_distinction_to_draft(draft, distinction)
        bonuses = draft.get_stat_bonuses_from_distinctions()
        assert bonuses == {"strength": 1}

    def test_get_all_stat_bonuses_combines_heritage_and_distinctions(
        self,
    ):
        """All bonuses aggregated from both species and distinctions."""
        distinction = DistinctionFactory()
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.strength_type,
            value_per_rank=10,
            description="",
        )
        draft = CharacterDraftFactory()
        self._add_distinction_to_draft(draft, distinction)
        bonuses = draft.get_all_stat_bonuses()
        assert bonuses["strength"] == 1

    def test_enforce_stat_caps_reduces_overcap(self):
        """Stat at 5 with +1 bonus should be reduced to 4."""
        distinction = DistinctionFactory()
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.strength_type,
            value_per_rank=10,
            description="",
        )
        draft = self._create_draft_with_stats(
            {
                "strength": 50,
                "agility": 20,
                "stamina": 20,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 20,
                "willpower": 20,
            }
        )
        self._add_distinction_to_draft(draft, distinction)

        adjustments = draft.enforce_stat_caps()

        draft.refresh_from_db()
        assert draft.draft_data["stats"]["strength"] == 40
        assert len(adjustments) == 1
        assert adjustments[0]["stat"] == "strength"
        assert adjustments[0]["old_display"] == 5
        assert adjustments[0]["new_display"] == 4

    def test_enforce_stat_caps_no_change_when_under_cap(self):
        """Stats under cap should not be modified."""
        distinction = DistinctionFactory()
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.strength_type,
            value_per_rank=10,
            description="",
        )
        draft = self._create_draft_with_stats(
            {
                "strength": 30,
                "agility": 20,
                "stamina": 20,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 20,
                "willpower": 20,
            }
        )
        self._add_distinction_to_draft(draft, distinction)

        adjustments = draft.enforce_stat_caps()
        assert adjustments == []
        draft.refresh_from_db()
        assert draft.draft_data["stats"]["strength"] == 30

    def test_enforce_stat_caps_no_stats_set(self):
        """No stats allocated yet means nothing to enforce."""
        draft = CharacterDraftFactory()
        adjustments = draft.enforce_stat_caps()
        assert adjustments == []
