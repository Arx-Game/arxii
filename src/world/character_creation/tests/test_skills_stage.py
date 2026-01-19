"""
Tests for Stage 5 (Path & Skills) validation in CharacterDraft.
"""

from django.test import TestCase
import pytest
from rest_framework import serializers

from world.character_creation.factories import CharacterDraftFactory
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

    def test_valid_skill_allocation(self):
        """Valid skill allocation should pass validation."""
        draft = CharacterDraftFactory()
        draft.draft_data["skills"] = {
            str(self.melee_skill.pk): 30,
            str(self.defense_skill.pk): 20,
        }
        draft.draft_data["specializations"] = {
            str(self.swords_spec.pk): 10,
        }
        draft.save()
        assert draft._is_path_skills_complete() is True
        # Also verify no exception raised
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
        assert draft._is_path_skills_complete() is False
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
        assert draft._is_path_skills_complete() is False
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
        assert draft._is_path_skills_complete() is False
        # Verify specific error message
        with pytest.raises(serializers.ValidationError) as exc_info:
            draft.validate_path_skills()
        assert "exceeds maximum" in str(exc_info.value)

    def test_empty_skills_is_valid(self):
        """Empty skill allocation is valid (player chose not to allocate)."""
        draft = CharacterDraftFactory()
        draft.draft_data["skills"] = {}
        draft.draft_data["specializations"] = {}
        draft.save()
        assert draft._is_path_skills_complete() is True
        # Also verify no exception raised
        draft.validate_path_skills()
