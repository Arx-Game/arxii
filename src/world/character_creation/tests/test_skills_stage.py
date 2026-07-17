"""
Tests for skill point allocation validation in CharacterDraft.

Skill allocation now lives under the Attributes & Skills stage (Stage 7);
it used to be part of "Path & Skills" (Stage 5) before the #2426 CG stage
restructure. ``draft.validate_path_skills()`` keeps its name (the
``draft_data["skills"]``/``draft_data["specializations"]`` keys are
unchanged) but its errors are now surfaced under ``Stage.ATTRIBUTES``.
"""

from django.test import TestCase
import pytest
from rest_framework import serializers

from world.character_creation.constants import Stage
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.validators import get_all_stage_errors
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.magic.factories import TraditionFactory
from world.skills.factories import SkillFactory, SkillPointBudgetFactory, SpecializationFactory
from world.traits.models import TraitCategory


class SkillsStageValidationTests(TestCase):
    """Test skill validation in CharacterDraft model."""

    @classmethod
    def setUpTestData(cls):
        cls.budget = SkillPointBudgetFactory(
            path_points=50,
            free_points=60,
            points_per_tier=10,
            specialization_unlock_threshold=30,
            max_skill_value=30,
            max_specialization_value=30,
        )
        cls.melee_skill = SkillFactory(
            trait__name="Melee Combat", trait__category=TraitCategory.COMBAT
        )
        cls.defense_skill = SkillFactory(
            trait__name="Defense", trait__category=TraitCategory.COMBAT
        )
        cls.swords_spec = SpecializationFactory(name="Swords", parent_skill=cls.melee_skill)
        cls.path = PathFactory(
            name="Test Path for Skills",
            stage=PathStage.PROSPECT,
            minimum_level=1,
        )
        cls.tradition = TraditionFactory()

    def test_valid_skill_allocation(self):
        """Valid skill allocation should pass validation."""
        draft = CharacterDraftFactory(selected_path=self.path, selected_tradition=self.tradition)
        draft.draft_data["skills"] = {
            str(self.melee_skill.pk): 30,
            str(self.defense_skill.pk): 20,
        }
        draft.draft_data["specializations"] = {
            str(self.swords_spec.pk): 10,
        }
        draft.save()
        # No exception raised
        draft.validate_path_skills()

    def test_over_budget_fails(self):
        """Exceeding point budget should fail validation."""
        draft = CharacterDraftFactory()
        # Create many skills to exceed budget
        skills = {}
        for _i in range(5):
            skill = SkillFactory()
            skills[str(skill.pk)] = 30
        draft.draft_data["skills"] = skills  # 150 points, over 110 budget
        draft.draft_data["specializations"] = {}
        draft.save()
        # Verify specific error message
        with pytest.raises(serializers.ValidationError) as exc_info:
            draft.validate_path_skills()
        assert "exceeds budget" in str(exc_info.value)

    def test_specialization_without_parent_fails(self):
        """Specialization without parent at threshold should fail."""
        draft = CharacterDraftFactory()
        draft.draft_data["skills"] = {
            str(self.melee_skill.pk): 20,  # Below 30 threshold
        }
        draft.draft_data["specializations"] = {
            str(self.swords_spec.pk): 10,
        }
        draft.save()
        # Verify specific error message
        with pytest.raises(serializers.ValidationError) as exc_info:
            draft.validate_path_skills()
        assert "requires parent skill" in str(exc_info.value)

    def test_skill_over_max_fails(self):
        """Skill value over CG max should fail."""
        draft = CharacterDraftFactory()
        draft.draft_data["skills"] = {
            str(self.melee_skill.pk): 40,  # Over 30 max
        }
        draft.save()
        # Verify specific error message
        with pytest.raises(serializers.ValidationError) as exc_info:
            draft.validate_path_skills()
        assert "exceeds maximum" in str(exc_info.value)

    def test_empty_skills_is_valid(self):
        """Empty skill allocation is valid (player chose not to allocate)."""
        draft = CharacterDraftFactory(selected_path=self.path, selected_tradition=self.tradition)
        draft.draft_data["skills"] = {}
        draft.draft_data["specializations"] = {}
        draft.save()
        # No exception raised
        draft.validate_path_skills()


class SkillStageMappingTests(TestCase):
    """Test that skill/path validation errors surface under the correct stage (#2426)."""

    @classmethod
    def setUpTestData(cls):
        cls.budget = SkillPointBudgetFactory(
            path_points=50,
            free_points=60,
            points_per_tier=10,
            specialization_unlock_threshold=30,
            max_skill_value=30,
            max_specialization_value=30,
        )
        cls.path = PathFactory(
            name="Test Path for Stage Mapping",
            stage=PathStage.PROSPECT,
            minimum_level=1,
        )
        cls.tradition = TraditionFactory()

    def test_missing_path_is_a_path_stage_error_independent_of_skills(self):
        """No path selected is a Path-stage error, regardless of skill data."""
        draft = CharacterDraftFactory(selected_path=None)
        draft.draft_data["skills"] = {}
        draft.save()
        errors = get_all_stage_errors(draft)
        assert "Select a path" in errors[Stage.PATH]

    def test_skill_budget_errors_surface_under_attributes_stage(self):
        """Over-budget skill allocation is an Attributes & Skills stage error, not a Path error."""
        draft = CharacterDraftFactory(selected_path=self.path, selected_tradition=self.tradition)
        skills = {}
        for _i in range(5):
            skill = SkillFactory()
            skills[str(skill.pk)] = 30
        draft.draft_data["skills"] = skills  # 150 points, over 110 budget
        draft.draft_data["specializations"] = {}
        draft.save()
        errors = get_all_stage_errors(draft)
        assert not errors[Stage.PATH]
        assert any("exceeds budget" in e for e in errors[Stage.ATTRIBUTES])
