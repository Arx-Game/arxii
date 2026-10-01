"""Tests for the requirement-type registry and check_requirements_for_technique (#4097).

concrete_requirement_types() discovers every concrete AbstractUnlockRequirement
subclass via apps.get_models() instead of a hand-maintained list, so a new
requirement type is picked up by every _check_requirements caller automatically.
check_requirements_for_technique is the fourth target wrapper (alongside
check_requirements_for_unlock / _thread_crossing / _path), gating technique
learning on TechniqueKnownRequirement and friends.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory
from world.progression.models import TechniqueKnownRequirement
from world.progression.services.spends import (
    check_requirements_for_technique,
    concrete_requirement_types,
)

# Pinned (#4097 fix round 2) — the previous version of this test re-derived
# "expected" with apps.get_models() filtered the exact same way
# concrete_requirement_types() filters internally, so a bug shared by both
# filters (e.g. a stray abstract=False on a base class) would pass silently.
# An explicit name list is an independent check: it fails loud when a type is
# added/removed/renamed, same as pinning any other registry.
EXPECTED_CONCRETE_REQUIREMENT_TYPE_NAMES = frozenset(
    {
        "AchievementRequirement",
        "ClassLevelRequirement",
        "CodexKnowledgeRequirement",
        "GiftHeldRequirement",
        "ItemRequirement",
        "LegendRequirement",
        "LevelRequirement",
        "MajorGiftTechniqueRequirement",
        "MultiClassRequirement",
        "RelationshipRequirement",
        "TechniqueKnownRequirement",
        "TierRequirement",
        "TraitRequirement",
    }
)


class RequirementRegistryTests(SimpleTestCase):
    """concrete_requirement_types() discovers every concrete subclass, not a fixed list."""

    def test_every_concrete_requirement_type_is_evaluated(self):
        names = {m.__name__ for m in concrete_requirement_types()}
        assert names == EXPECTED_CONCRETE_REQUIREMENT_TYPE_NAMES

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
