"""
Tests for character creation models.
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import (
    REQUIRED_STATS,
    STAT_DEFAULT_VALUE,
)
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    StartingAreaFactory,
)
from world.character_creation.models import (
    CharacterDraft,
    StartingArea,
)
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.forms.factories import BuildFactory, HeightBandFactory
from world.magic.factories import TraditionFactory
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
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
    """Test stat allocation with simplified 1-5 scale and budget system."""

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

        # Ensure all 12 primary stats exist
        for name in REQUIRED_STATS:
            Trait.objects.get_or_create(
                name=name,
                defaults={
                    "trait_type": TraitType.STAT,
                    "description": f"{name.capitalize()} stat",
                },
            )

    def _all_stats_at(self, value: int) -> dict[str, int]:
        """Helper: return all 12 stats set to the given value."""
        return dict.fromkeys(REQUIRED_STATS, value)

    def _budget_balanced_stats(self) -> dict[str, int]:
        """Helper: return stats that sum to the base budget (24)."""
        # All at 2 = 12 * 2 = 24
        return self._all_stats_at(STAT_DEFAULT_VALUE)

    # --- calculate_stat_budget ---

    def test_calculate_stat_budget_no_bonuses(self):
        """Budget is 12 * 2 = 24 with no bonuses."""
        assert self.draft.calculate_stat_budget() == STAT_DEFAULT_VALUE * len(REQUIRED_STATS)

    # --- calculate_points_remaining ---

    def test_calculate_points_remaining_no_stats(self):
        """No stats allocated returns 0 remaining (base budget - default allocation)."""
        remaining = self.draft.calculate_points_remaining()
        assert remaining == 0

    def test_calculate_points_remaining_all_at_default(self):
        """All stats at default value means 0 remaining."""
        self.draft.draft_data = {"stats": self._budget_balanced_stats()}
        self.draft.save()
        assert self.draft.calculate_points_remaining() == 0

    def test_calculate_points_remaining_redistributed(self):
        """Redistributed stats still sum to budget = 0 remaining."""
        stats = self._all_stats_at(STAT_DEFAULT_VALUE)
        # Move 1 point from first stat to second
        stat_names = list(stats.keys())
        stats[stat_names[0]] = 1
        stats[stat_names[1]] = 3
        self.draft.draft_data = {"stats": stats}
        self.draft.save()
        assert self.draft.calculate_points_remaining() == 0

    def test_calculate_points_remaining_under_allocated(self):
        """Under-allocated stats return positive remaining."""
        stats = self._all_stats_at(1)  # 12 * 1 = 12, budget = 24, remaining = 12
        self.draft.draft_data = {"stats": stats}
        self.draft.save()
        assert self.draft.calculate_points_remaining() == 12

    def test_calculate_points_remaining_over_allocated(self):
        """Over-allocated stats return negative remaining."""
        stats = self._all_stats_at(3)  # 12 * 3 = 36, budget = 24, remaining = -12
        self.draft.draft_data = {"stats": stats}
        self.draft.save()
        assert self.draft.calculate_points_remaining() == -12

    # --- Validation via _is_attributes_complete ---

    def test_validation_missing_stats(self):
        """Validation fails with missing stats."""
        self.draft.draft_data = {"stats": {"strength": 2, "agility": 2}}
        self.draft.save()
        assert not self.draft._is_attributes_complete()

    def test_validation_stat_below_min(self):
        """Validation fails with stat below minimum (1)."""
        stats = self._budget_balanced_stats()
        stat_names = list(stats.keys())
        stats[stat_names[0]] = 0  # Below STAT_MIN_VALUE
        self.draft.draft_data = {"stats": stats}
        self.draft.save()
        assert not self.draft._is_attributes_complete()

    def test_validation_stat_above_max(self):
        """Validation fails with stat above maximum (5)."""
        stats = self._budget_balanced_stats()
        stat_names = list(stats.keys())
        stats[stat_names[0]] = 6  # Above STAT_MAX_VALUE
        self.draft.draft_data = {"stats": stats}
        self.draft.save()
        assert not self.draft._is_attributes_complete()

    def test_validation_non_integer_value(self):
        """Validation fails with non-integer values."""
        stats = self._budget_balanced_stats()
        stat_names = list(stats.keys())
        stats[stat_names[0]] = 2.5
        self.draft.draft_data = {"stats": stats}
        self.draft.save()
        assert not self.draft._is_attributes_complete()

    def test_validation_points_remaining_positive(self):
        """Validation fails when points remaining > 0."""
        stats = self._all_stats_at(1)  # Under budget
        self.draft.draft_data = {"stats": stats}
        self.draft.save()
        assert not self.draft._is_attributes_complete()

    def test_validation_over_budget(self):
        """Validation fails when over budget."""
        stats = self._all_stats_at(3)  # Over budget
        self.draft.draft_data = {"stats": stats}
        self.draft.save()
        assert not self.draft._is_attributes_complete()

    def test_validation_all_valid(self):
        """Validation passes: all 12 stats present, each 1-5, sum == budget."""
        stats = self._budget_balanced_stats()
        self.draft.draft_data = {"stats": stats}
        self.draft.save()
        assert self.draft._is_attributes_complete()

    def test_stage_completion_includes_attributes(self):
        """Stage completion dict includes attributes stage."""
        stats = self._budget_balanced_stats()
        self.draft.draft_data = {"stats": stats}
        self.draft.save()
        stage_completion = self.draft.get_stage_completion()
        assert CharacterDraft.Stage.ATTRIBUTES in stage_completion
        assert stage_completion[CharacterDraft.Stage.ATTRIBUTES] is True

    # --- calculate_final_stats ---

    def test_calculate_final_stats_returns_allocated_values(self):
        """calculate_final_stats returns stats as stored (1-5 scale), no bonuses on top."""
        stats = self._budget_balanced_stats()
        stat_names = list(stats.keys())
        stats[stat_names[0]] = 1
        stats[stat_names[1]] = 3
        self.draft.draft_data = {"stats": stats}
        self.draft.save()
        final = self.draft.calculate_final_stats()
        assert final[stat_names[0]] == 1
        assert final[stat_names[1]] == 3
        # Unset stats should get default value
        for name in REQUIRED_STATS:
            assert name in final

    def test_calculate_final_stats_defaults_for_missing(self):
        """Missing stats default to STAT_DEFAULT_VALUE."""
        self.draft.draft_data = {"stats": {}}
        self.draft.save()
        final = self.draft.calculate_final_stats()
        for name in REQUIRED_STATS:
            assert final[name] == STAT_DEFAULT_VALUE


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
        cls.tradition = TraditionFactory()

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
            selected_tradition=self.tradition,
            draft_data={"skills": {}, "specializations": {}},
        )
        # With empty skills but path and tradition selected, stage is complete
        # (validation passes because total spent <= budget)
        completion = draft.get_stage_completion()
        self.assertTrue(completion[CharacterDraft.Stage.PATH_SKILLS])


class DistinctionStatBonusTests(TestCase):
    """Test distinction stat bonuses affect budget, not individual stat caps."""

    @classmethod
    def setUpTestData(cls):
        cls.stat_category = ModifierCategoryFactory(name="stat")
        cls.strength_type = ModifierTargetFactory(name="strength", category=cls.stat_category)
        cls.agility_type = ModifierTargetFactory(name="agility", category=cls.stat_category)

    def _add_distinction_to_draft(self, draft: CharacterDraft, distinction: object) -> None:
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

    def test_get_all_stat_bonuses_combines_heritage_and_distinctions(self):
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

    def test_budget_increases_with_positive_distinction_bonus(self):
        """Budget = 24 + 1 = 25 with a +1 distinction bonus."""
        distinction = DistinctionFactory()
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.strength_type,
            value_per_rank=10,
            description="",
        )
        draft = CharacterDraftFactory()
        self._add_distinction_to_draft(draft, distinction)
        base = STAT_DEFAULT_VALUE * len(REQUIRED_STATS)
        assert draft.calculate_stat_budget() == base + 1

    def test_budget_decreases_with_negative_distinction_bonus(self):
        """Budget = 24 - 1 = 23 with a -1 distinction penalty."""
        distinction = DistinctionFactory()
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.strength_type,
            value_per_rank=-10,
            description="",
        )
        draft = CharacterDraftFactory()
        self._add_distinction_to_draft(draft, distinction)
        base = STAT_DEFAULT_VALUE * len(REQUIRED_STATS)
        assert draft.calculate_stat_budget() == base - 1

    def test_stacking_bonuses_increase_budget(self):
        """Multiple distinction bonuses stack and increase budget."""
        d1 = DistinctionFactory()
        DistinctionEffectFactory(
            distinction=d1,
            target=self.strength_type,
            value_per_rank=10,
            description="",
        )
        d2 = DistinctionFactory()
        DistinctionEffectFactory(
            distinction=d2,
            target=self.agility_type,
            value_per_rank=10,
            description="",
        )
        draft = CharacterDraftFactory()
        self._add_distinction_to_draft(draft, d1)
        self._add_distinction_to_draft(draft, d2)
        base = STAT_DEFAULT_VALUE * len(REQUIRED_STATS)
        assert draft.calculate_stat_budget() == base + 2


class CGPointsCalculationTests(TestCase):
    """Tests for CG points computation from actual data sources."""

    def test_no_beginnings_no_distinctions_returns_zero(self):
        """Spent is 0 when draft has no beginnings or distinctions."""
        draft = CharacterDraftFactory(selected_beginnings=None)
        assert draft.calculate_cg_points_spent() == 0

    def test_beginnings_cost_included(self):
        """Beginnings cg_point_cost is counted as spent."""
        beginnings = BeginningsFactory(cg_point_cost=15)
        draft = CharacterDraftFactory(selected_beginnings=beginnings)
        assert draft.calculate_cg_points_spent() == 15

    def test_distinction_costs_included(self):
        """Distinction costs from draft_data are summed."""
        draft = CharacterDraftFactory(selected_beginnings=None)
        draft.draft_data["distinctions"] = [
            {"distinction_id": 1, "cost": 5},
            {"distinction_id": 2, "cost": -3},
        ]
        draft.save(update_fields=["draft_data"])
        assert draft.calculate_cg_points_spent() == 2

    def test_beginnings_plus_distinctions(self):
        """Both beginnings and distinction costs are summed."""
        beginnings = BeginningsFactory(cg_point_cost=20)
        draft = CharacterDraftFactory(selected_beginnings=beginnings)
        draft.draft_data["distinctions"] = [
            {"distinction_id": 1, "cost": 10},
        ]
        draft.save(update_fields=["draft_data"])
        assert draft.calculate_cg_points_spent() == 30

    def test_remaining_accounts_for_spent(self):
        """Remaining = budget - spent."""
        from world.character_creation.models import CGPointBudget

        beginnings = BeginningsFactory(cg_point_cost=25)
        draft = CharacterDraftFactory(selected_beginnings=beginnings)
        budget = CGPointBudget.get_active_budget()
        assert draft.calculate_cg_points_remaining() == budget - 25
