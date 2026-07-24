"""Tests for Path TraitRequirements: hybrid path entry gating + selectors (#2538)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import (
    CharacterClassFactory,
    CharacterClassLevelFactory,
    PathFactory,
)
from world.classes.models import PathStage
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
from world.progression.exceptions import PathRequirementsNotMet
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.models import CodexKnowledgeRequirement, TraitRequirement
from world.progression.selectors import eligible_advanced_paths_for
from world.progression.services.advancement import cross_into_path
from world.progression.services.spends import check_requirements_for_path
from world.roster.factories import RosterEntryFactory, RosterFactory
from world.traits.factories import CharacterTraitValueFactory, SkillTraitFactory


class CheckRequirementsForPathTests(TestCase):
    """Unit tests for the check_requirements_for_path service wrapper."""

    def test_fail_open_when_no_requirements(self):
        """A path with no authored TraitRequirements returns (True, [])."""
        path = PathFactory()
        sheet = CharacterSheetFactory()
        met, failed = check_requirements_for_path(sheet.character, path)
        self.assertTrue(met)
        self.assertEqual(failed, [])

    def test_returns_true_when_requirements_met(self):
        """A character meeting all TraitRequirements passes."""
        path = PathFactory()
        trait = SkillTraitFactory()
        sheet = CharacterSheetFactory()
        CharacterTraitValueFactory(character=sheet, trait=trait, value=40)
        TraitRequirement.objects.create(path=path, trait=trait, minimum_value=30, is_active=True)
        met, failed = check_requirements_for_path(sheet.character, path)
        self.assertTrue(met)
        self.assertEqual(failed, [])

    def test_returns_false_when_requirements_not_met(self):
        """A character not meeting TraitRequirements fails with messages."""
        path = PathFactory()
        trait = SkillTraitFactory(name="persuasion")
        sheet = CharacterSheetFactory()
        CharacterTraitValueFactory(character=sheet, trait=trait, value=20)
        TraitRequirement.objects.create(path=path, trait=trait, minimum_value=30, is_active=True)
        met, failed = check_requirements_for_path(sheet.character, path)
        self.assertFalse(met)
        self.assertEqual(len(failed), 1)
        self.assertIn("persuasion", failed[0].lower())

    def test_inactive_requirement_is_ignored(self):
        """An is_active=False requirement does not gate."""
        path = PathFactory()
        trait = SkillTraitFactory()
        sheet = CharacterSheetFactory()
        TraitRequirement.objects.create(path=path, trait=trait, minimum_value=100, is_active=False)
        met, _failed = check_requirements_for_path(sheet.character, path)
        self.assertTrue(met)


class PathRequirementsNotMetTests(TestCase):
    """Unit tests for the PathRequirementsNotMet exception."""

    def test_carries_user_message(self):
        """The exception carries a descriptive user_message."""
        exc = PathRequirementsNotMet(
            path_name="Voice/Steel Hybrid",
            failed_messages=["Need persuasion 3.0, have 2.0"],
        )
        self.assertIn("Voice/Steel Hybrid", exc.user_message)
        self.assertIn("persuasion", exc.user_message.lower())

    def test_subclasses_class_level_advancement_error(self):
        """The exception subclasses ClassLevelAdvancementError."""
        from world.progression.exceptions import ClassLevelAdvancementError

        self.assertTrue(issubclass(PathRequirementsNotMet, ClassLevelAdvancementError))


class CrossIntoPathGateTests(TestCase):
    """Tests for the requirement gate in cross_into_path."""

    def test_raises_when_requirements_not_met(self):
        """cross_into_path raises PathRequirementsNotMet when requirements are unmet."""
        parent = PathFactory(stage=PathStage.PROSPECT)
        hybrid = PathFactory(stage=PathStage.POTENTIAL)
        hybrid.parent_paths.add(parent)
        trait = SkillTraitFactory()
        sheet = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=sheet, path=parent)
        TraitRequirement.objects.create(path=hybrid, trait=trait, minimum_value=30, is_active=True)
        # Character does NOT have the trait at all — should fail
        with self.assertRaises(PathRequirementsNotMet):
            cross_into_path(sheet, hybrid)

    def test_succeeds_when_requirements_met(self):
        """cross_into_path succeeds and writes CharacterPathHistory when requirements are met."""
        parent = PathFactory(stage=PathStage.PROSPECT)
        hybrid = PathFactory(stage=PathStage.POTENTIAL)
        hybrid.parent_paths.add(parent)
        trait = SkillTraitFactory()
        sheet = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=sheet, path=parent)
        CharacterTraitValueFactory(character=sheet, trait=trait, value=40)
        TraitRequirement.objects.create(path=hybrid, trait=trait, minimum_value=30, is_active=True)
        result = cross_into_path(sheet, hybrid)
        self.assertIsNotNone(result)
        # Verify the path history was written
        from world.progression.models import CharacterPathHistory

        self.assertTrue(CharacterPathHistory.objects.filter(character=sheet, path=hybrid).exists())

    def test_succeeds_when_no_requirements(self):
        """cross_into_path succeeds for a path with no requirements (fail-open)."""
        parent = PathFactory(stage=PathStage.PROSPECT)
        child = PathFactory(stage=PathStage.POTENTIAL)
        child.parent_paths.add(parent)
        sheet = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=sheet, path=parent)
        result = cross_into_path(sheet, child)
        self.assertIsNotNone(result)


class EligibleAdvancedPathsForTests(TestCase):
    """Tests for the requirement filter in eligible_advanced_paths_for."""

    def _setup_character_at_level_2(self, sheet):
        """Set up a character at level 2 (next level 3 = POTENTIAL semi-crossing)."""
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(
            character=sheet,
            character_class=char_class,
            level=2,
            is_primary=True,
        )
        sheet.invalidate_class_level_cache()

    def test_filters_out_paths_with_unmet_requirements(self):
        """Paths with unmet TraitRequirements are not in the eligible list."""
        parent = PathFactory(stage=PathStage.PROSPECT)
        eligible_child = PathFactory(stage=PathStage.POTENTIAL, is_active=True)
        gated_child = PathFactory(stage=PathStage.POTENTIAL, is_active=True)
        eligible_child.parent_paths.add(parent)
        gated_child.parent_paths.add(parent)
        trait = SkillTraitFactory()
        sheet = CharacterSheetFactory()
        self._setup_character_at_level_2(sheet)
        CharacterPathHistoryFactory(character=sheet, path=parent)
        # gated_child requires trait at 30; character has nothing
        TraitRequirement.objects.create(
            path=gated_child, trait=trait, minimum_value=30, is_active=True
        )
        eligible = eligible_advanced_paths_for(sheet)
        eligible_ids = [p.pk for p in eligible]
        self.assertIn(eligible_child.pk, eligible_ids)
        self.assertNotIn(gated_child.pk, eligible_ids)

    def test_includes_paths_with_met_requirements(self):
        """Paths with met TraitRequirements are in the eligible list."""
        parent = PathFactory(stage=PathStage.PROSPECT)
        gated_child = PathFactory(stage=PathStage.POTENTIAL, is_active=True)
        gated_child.parent_paths.add(parent)
        trait = SkillTraitFactory()
        sheet = CharacterSheetFactory()
        self._setup_character_at_level_2(sheet)
        CharacterPathHistoryFactory(character=sheet, path=parent)
        CharacterTraitValueFactory(character=sheet, trait=trait, value=40)
        TraitRequirement.objects.create(
            path=gated_child, trait=trait, minimum_value=30, is_active=True
        )
        eligible = eligible_advanced_paths_for(sheet)
        eligible_ids = [p.pk for p in eligible]
        self.assertIn(gated_child.pk, eligible_ids)

    def test_includes_paths_with_no_requirements(self):
        """Paths with no requirements are always eligible (fail-open)."""
        parent = PathFactory(stage=PathStage.PROSPECT)
        child = PathFactory(stage=PathStage.POTENTIAL, is_active=True)
        child.parent_paths.add(parent)
        sheet = CharacterSheetFactory()
        self._setup_character_at_level_2(sheet)
        CharacterPathHistoryFactory(character=sheet, path=parent)
        eligible = eligible_advanced_paths_for(sheet)
        eligible_ids = [p.pk for p in eligible]
        self.assertIn(child.pk, eligible_ids)


class HybridFromEitherParentTests(TestCase):
    """A hybrid path reachable from either parent, gated by the same requirements."""

    def test_hybrid_eligible_from_either_parent(self):
        """A hybrid with two parents is reachable from both when requirements are met."""
        parent_a = PathFactory(stage=PathStage.PROSPECT)
        parent_b = PathFactory(stage=PathStage.PROSPECT)
        hybrid = PathFactory(stage=PathStage.POTENTIAL, is_active=True)
        hybrid.parent_paths.add(parent_a, parent_b)
        trait = SkillTraitFactory()
        TraitRequirement.objects.create(path=hybrid, trait=trait, minimum_value=30, is_active=True)

        # Character on parent_a, with the trait
        sheet_a = CharacterSheetFactory()
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(
            character=sheet_a,
            character_class=char_class,
            level=2,
            is_primary=True,
        )
        sheet_a.invalidate_class_level_cache()
        CharacterPathHistoryFactory(character=sheet_a, path=parent_a)
        CharacterTraitValueFactory(character=sheet_a, trait=trait, value=40)
        eligible_a = eligible_advanced_paths_for(sheet_a)
        self.assertIn(hybrid, eligible_a)

        # Character on parent_b, with the trait
        sheet_b = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=sheet_b,
            character_class=char_class,
            level=2,
            is_primary=True,
        )
        sheet_b.invalidate_class_level_cache()
        CharacterPathHistoryFactory(character=sheet_b, path=parent_b)
        CharacterTraitValueFactory(character=sheet_b, trait=trait, value=40)
        eligible_b = eligible_advanced_paths_for(sheet_b)
        self.assertIn(hybrid, eligible_b)

    def test_three_parent_hybrid_reachable_from_any(self):
        """A hybrid with 3 parents is reachable from any of them when requirements are met."""
        parents = [PathFactory(stage=PathStage.PROSPECT) for _ in range(3)]
        hybrid = PathFactory(stage=PathStage.POTENTIAL, is_active=True)
        for p in parents:
            hybrid.parent_paths.add(p)
        trait = SkillTraitFactory()
        TraitRequirement.objects.create(path=hybrid, trait=trait, minimum_value=30, is_active=True)
        char_class = CharacterClassFactory()
        for parent in parents:
            sheet = CharacterSheetFactory()
            CharacterClassLevelFactory(
                character=sheet,
                character_class=char_class,
                level=2,
                is_primary=True,
            )
            sheet.invalidate_class_level_cache()
            CharacterPathHistoryFactory(character=sheet, path=parent)
            CharacterTraitValueFactory(character=sheet, trait=trait, value=40)
            eligible = eligible_advanced_paths_for(sheet)
            self.assertIn(hybrid, eligible, f"Hybrid not eligible from {parent.name}")


class CodexKnowledgeRequirementTests(TestCase):
    """Tests for CodexKnowledgeRequirement gating (#2603)."""

    def _make_sheet_with_roster_entry(self):
        """Create a CharacterSheet with a linked RosterEntry for codex knowledge."""
        sheet = CharacterSheetFactory()
        roster = RosterFactory()
        RosterEntryFactory(character_sheet=sheet, roster=roster)
        return sheet

    def test_gate_passes_when_codex_entry_is_known(self):
        """A character with KNOWN codex knowledge passes the gate."""
        path = PathFactory()
        entry = CodexEntryFactory()
        sheet = self._make_sheet_with_roster_entry()
        CharacterCodexKnowledgeFactory(
            roster_entry=sheet.roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        CodexKnowledgeRequirement.objects.create(path=path, codex_entry=entry, is_active=True)
        met, failed = check_requirements_for_path(sheet.character, path)
        self.assertTrue(met)
        self.assertEqual(failed, [])

    def test_gate_fails_when_codex_entry_is_uncovered(self):
        """A character with UNCOVERED (not yet learned) codex knowledge fails."""
        path = PathFactory()
        entry = CodexEntryFactory()
        sheet = self._make_sheet_with_roster_entry()
        CharacterCodexKnowledgeFactory(
            roster_entry=sheet.roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.UNCOVERED,
        )
        CodexKnowledgeRequirement.objects.create(path=path, codex_entry=entry, is_active=True)
        met, failed = check_requirements_for_path(sheet.character, path)
        self.assertFalse(met)
        self.assertEqual(len(failed), 1)
        self.assertIn(entry.name, failed[0])

    def test_gate_fails_when_codex_entry_is_absent(self):
        """A character with no CharacterCodexKnowledge row for the entry fails."""
        path = PathFactory()
        entry = CodexEntryFactory()
        sheet = self._make_sheet_with_roster_entry()
        CodexKnowledgeRequirement.objects.create(path=path, codex_entry=entry, is_active=True)
        met, failed = check_requirements_for_path(sheet.character, path)
        self.assertFalse(met)
        self.assertEqual(len(failed), 1)

    def test_fail_open_when_no_requirement_authored(self):
        """A path with no CodexKnowledgeRequirement passes (fail-open)."""
        path = PathFactory()
        sheet = self._make_sheet_with_roster_entry()
        met, failed = check_requirements_for_path(sheet.character, path)
        self.assertTrue(met)
        self.assertEqual(failed, [])

    def test_inactive_requirement_is_ignored(self):
        """An is_active=False CodexKnowledgeRequirement does not gate."""
        path = PathFactory()
        entry = CodexEntryFactory()
        sheet = self._make_sheet_with_roster_entry()
        CodexKnowledgeRequirement.objects.create(path=path, codex_entry=entry, is_active=False)
        met, _failed = check_requirements_for_path(sheet.character, path)
        self.assertTrue(met)

    def test_is_met_degrades_gracefully_without_sheet(self):
        """is_met_by_character returns False (not crash) when no CharacterSheet."""
        from evennia_extensions.factories import CharacterFactory

        path = PathFactory()
        entry = CodexEntryFactory()
        req = CodexKnowledgeRequirement.objects.create(path=path, codex_entry=entry, is_active=True)
        bare_obj = CharacterFactory()
        met, msg = req.is_met_by_character(bare_obj)
        self.assertFalse(met)
        self.assertIn(entry.name, msg)


class CodexKnowledgeSelectorTests(TestCase):
    """Tests for CodexKnowledgeRequirement filtering in eligible_advanced_paths_for."""

    def _setup_character_at_level_2(self, sheet):
        """Set up a character at level 2 (next level 3 = POTENTIAL semi-crossing)."""
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(
            character=sheet,
            character_class=char_class,
            level=2,
            is_primary=True,
        )
        sheet.invalidate_class_level_cache()

    def _make_sheet_with_roster_entry(self):
        """Create a CharacterSheet with a linked RosterEntry for codex knowledge."""
        sheet = CharacterSheetFactory()
        roster = RosterFactory()
        RosterEntryFactory(character_sheet=sheet, roster=roster)
        return sheet

    def test_filters_out_paths_with_unmet_codex_requirement(self):
        """Paths with unmet CodexKnowledgeRequirement are not in the eligible list."""
        parent = PathFactory(stage=PathStage.PROSPECT)
        eligible_child = PathFactory(stage=PathStage.POTENTIAL, is_active=True)
        gated_child = PathFactory(stage=PathStage.POTENTIAL, is_active=True)
        eligible_child.parent_paths.add(parent)
        gated_child.parent_paths.add(parent)
        entry = CodexEntryFactory()
        sheet = self._make_sheet_with_roster_entry()
        self._setup_character_at_level_2(sheet)
        CharacterPathHistoryFactory(character=sheet, path=parent)
        CodexKnowledgeRequirement.objects.create(
            path=gated_child, codex_entry=entry, is_active=True
        )
        eligible = eligible_advanced_paths_for(sheet)
        eligible_ids = [p.pk for p in eligible]
        self.assertIn(eligible_child.pk, eligible_ids)
        self.assertNotIn(gated_child.pk, eligible_ids)

    def test_includes_paths_with_met_codex_requirement(self):
        """Paths with met CodexKnowledgeRequirement are in the eligible list."""
        parent = PathFactory(stage=PathStage.PROSPECT)
        gated_child = PathFactory(stage=PathStage.POTENTIAL, is_active=True)
        gated_child.parent_paths.add(parent)
        entry = CodexEntryFactory()
        sheet = self._make_sheet_with_roster_entry()
        self._setup_character_at_level_2(sheet)
        CharacterPathHistoryFactory(character=sheet, path=parent)
        CharacterCodexKnowledgeFactory(
            roster_entry=sheet.roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        CodexKnowledgeRequirement.objects.create(
            path=gated_child, codex_entry=entry, is_active=True
        )
        eligible = eligible_advanced_paths_for(sheet)
        eligible_ids = [p.pk for p in eligible]
        self.assertIn(gated_child.pk, eligible_ids)
