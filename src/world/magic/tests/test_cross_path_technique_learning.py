"""Tests for cross-path technique learning via stat/skill requirements (#2538)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.magic.factories import (
    GiftFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)
from world.magic.services.gift_acquisition import can_learn_technique
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.models import TraitRequirement
from world.traits.factories import CharacterTraitValueFactory, SkillTraitFactory


class CanLearnTechniqueCrossPathTests(TestCase):
    """Tests for the cross-path learning branch of can_learn_technique (#2538)."""

    def _setup_character_on_path(self, path, trait=None, trait_value=None):
        """Create a character on *path* with optional trait value set."""
        sheet = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=sheet, path=path)
        if trait is not None and trait_value is not None:
            CharacterTraitValueFactory(character=sheet, trait=trait, value=trait_value)
        return sheet

    def _make_technique_with_style(self, allowed_paths):
        """Create a technique whose style is restricted to *allowed_paths*."""
        gift = GiftFactory()
        style = TechniqueStyleFactory()
        if allowed_paths:
            style.allowed_paths.set(allowed_paths)
        return TechniqueFactory(gift=gift, style=style)

    def test_cross_path_allowed_when_requirements_met(self):
        """A character on Path A can learn a Path-B technique when they meet B's requirements."""
        path_a = PathFactory()
        path_b = PathFactory()
        trait = SkillTraitFactory()
        # path_b requires trait >= 30
        TraitRequirement.objects.create(path=path_b, trait=trait, minimum_value=30, is_active=True)
        technique = self._make_technique_with_style([path_b])
        # Character on path_a, with trait at 40 (meets path_b's requirement)
        sheet = self._setup_character_on_path(path_a, trait=trait, trait_value=40)
        self.assertTrue(can_learn_technique(sheet, technique))

    def test_cross_path_blocked_when_requirements_not_met(self):
        """Cannot learn a cross-path technique without meeting its requirements."""
        path_a = PathFactory()
        path_b = PathFactory()
        trait = SkillTraitFactory()
        TraitRequirement.objects.create(path=path_b, trait=trait, minimum_value=30, is_active=True)
        technique = self._make_technique_with_style([path_b])
        # Character on path_a, with trait at 20 (below path_b's requirement of 30)
        sheet = self._setup_character_on_path(path_a, trait=trait, trait_value=20)
        self.assertFalse(can_learn_technique(sheet, technique))

    def test_cross_path_blocked_when_trait_absent(self):
        """Cannot learn a cross-path technique without the required trait at all."""
        path_a = PathFactory()
        path_b = PathFactory()
        trait = SkillTraitFactory()
        TraitRequirement.objects.create(path=path_b, trait=trait, minimum_value=30, is_active=True)
        technique = self._make_technique_with_style([path_b])
        # Character on path_a, no trait value at all
        sheet = self._setup_character_on_path(path_a)
        self.assertFalse(can_learn_technique(sheet, technique))

    def test_cross_path_allowed_when_any_allowed_path_requirements_met(self):
        """If multiple paths are in allowed_paths, meeting any one's requirements suffices."""
        path_a = PathFactory()
        path_b = PathFactory()
        path_c = PathFactory()
        trait_b = SkillTraitFactory()
        trait_c = SkillTraitFactory()
        # path_b requires trait_b >= 30; path_c requires trait_c >= 30
        TraitRequirement.objects.create(
            path=path_b, trait=trait_b, minimum_value=30, is_active=True
        )
        TraitRequirement.objects.create(
            path=path_c, trait=trait_c, minimum_value=30, is_active=True
        )
        # Technique allows path_b and path_c
        technique = self._make_technique_with_style([path_b, path_c])
        # Character on path_a, meets path_c's requirement but not path_b's
        sheet = self._setup_character_on_path(path_a, trait=trait_c, trait_value=40)
        self.assertTrue(can_learn_technique(sheet, technique))

    def test_cross_path_blocked_when_allowed_path_has_no_requirements(self):
        """A path with no authored requirements does NOT open cross-learning."""
        path_a = PathFactory()
        path_b = PathFactory()
        # No TraitRequirements on path_b — allowed_paths restriction stands
        technique = self._make_technique_with_style([path_b])
        sheet = self._setup_character_on_path(path_a)
        self.assertFalse(can_learn_technique(sheet, technique))

    def test_current_path_still_works(self):
        """A character on a path in allowed_paths can learn without cross-path check."""
        path_a = PathFactory()
        technique = self._make_technique_with_style([path_a])
        sheet = self._setup_character_on_path(path_a)
        self.assertTrue(can_learn_technique(sheet, technique))

    def test_blank_allowed_paths_still_unrestricted(self):
        """A technique style with no allowed_paths restriction is open to all."""
        path_a = PathFactory()
        technique = self._make_technique_with_style([])  # blank = all paths
        sheet = self._setup_character_on_path(path_a)
        self.assertTrue(can_learn_technique(sheet, technique))

    def test_no_path_character_unrestricted(self):
        """A character with no path history is unrestricted."""
        technique = self._make_technique_with_style([PathFactory()])
        sheet = CharacterSheetFactory()  # no path history
        self.assertTrue(can_learn_technique(sheet, technique))
