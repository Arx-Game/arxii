"""Tests for the requirement-type registry and check_requirements_for_technique (#4097).

concrete_requirement_types() discovers every concrete AbstractUnlockRequirement
subclass via apps.get_models() instead of a hand-maintained list, so a new
requirement type is picked up by every _check_requirements caller automatically.
check_requirements_for_technique is the fourth target wrapper (alongside
check_requirements_for_unlock / _thread_crossing / _path), gating technique
learning on TechniqueKnownRequirement and friends.
"""

from __future__ import annotations

from django.apps import apps
from django.test import SimpleTestCase, TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory
from world.progression.models import TechniqueKnownRequirement
from world.progression.models.unlocks import AbstractUnlockRequirement
from world.progression.services.spends import (
    check_requirements_for_technique,
    concrete_requirement_types,
)


class RequirementRegistryTests(SimpleTestCase):
    """concrete_requirement_types() discovers every concrete subclass, not a fixed list."""

    def test_every_concrete_requirement_type_is_evaluated(self):
        expected = {
            m
            for m in apps.get_models()
            if issubclass(m, AbstractUnlockRequirement) and not m._meta.abstract
        }
        assert set(concrete_requirement_types()) == expected
        assert len(expected) >= 13  # 11 existing + GiftHeld + TechniqueKnown

    def test_sorted_by_name(self):
        names = [m.__name__ for m in concrete_requirement_types()]
        assert names == sorted(names)


class CheckRequirementsForTechniqueTests(TestCase):
    """check_requirements_for_technique gates learning a technique on its requirements."""

    def test_unmet_requirement_fails(self):
        technique = TechniqueFactory()
        prerequisite = TechniqueFactory()
        sheet = CharacterSheetFactory()
        TechniqueKnownRequirement.objects.create(
            technique=technique, required_technique=prerequisite, is_active=True
        )

        met, failed = check_requirements_for_technique(sheet.character, technique)

        assert met is False
        assert len(failed) == 1
        assert prerequisite.name in failed[0]

    def test_met_requirement_passes(self):
        technique = TechniqueFactory()
        prerequisite = TechniqueFactory()
        sheet = CharacterSheetFactory()
        CharacterTechniqueFactory(character=sheet, technique=prerequisite)
        TechniqueKnownRequirement.objects.create(
            technique=technique, required_technique=prerequisite, is_active=True
        )

        met, failed = check_requirements_for_technique(sheet.character, technique)

        assert met is True
        assert failed == []

    def test_inactive_requirement_is_ignored(self):
        technique = TechniqueFactory()
        prerequisite = TechniqueFactory()
        sheet = CharacterSheetFactory()
        TechniqueKnownRequirement.objects.create(
            technique=technique, required_technique=prerequisite, is_active=False
        )

        met, failed = check_requirements_for_technique(sheet.character, technique)

        assert met is True
        assert failed == []

    def test_fail_open_when_no_requirements(self):
        technique = TechniqueFactory()
        sheet = CharacterSheetFactory()

        met, failed = check_requirements_for_technique(sheet.character, technique)

        assert met is True
        assert failed == []
