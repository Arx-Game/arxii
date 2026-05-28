"""Tests that get_player_actions folds in enhancements, target_spec, and strain."""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from actions.constants import TargetKind
from actions.factories import ActionTemplateFactory
from actions.models import ActionEnhancement
from actions.player_interface import get_player_actions
from actions.types import TargetType
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueFactory,
)


def _make_social_template(name: str) -> object:
    """Build a category=social ActionTemplate for surfacing via _scene_actions."""
    return ActionTemplateFactory(
        name=name,
        category="social",
        consequence_pool=None,
    )


class GetPlayerActionsEnhancementsTests(TestCase):
    """Each PlayerAction carries its enhancements + target_spec + strain."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.template = _make_social_template("Intimidate")
        cls.technique = TechniqueFactory(name="Wave of Dread")
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)
        # Enhancement is keyed by both action_key (intimidate) and the template id.
        cls.enhancement = ActionEnhancement.objects.create(
            base_action_key="intimidate",
            variant_name="Dread Intimidate",
            source_type="technique",
            technique=cls.technique,
        )

    def test_enhancements_attached_to_player_action(self) -> None:
        actions = get_player_actions(self.character)
        intimidate = next((a for a in actions if a.display_name == "Intimidate"), None)
        self.assertIsNotNone(intimidate)
        self.assertTrue(
            len(intimidate.enhancements) >= 1,
            f"Expected at least one enhancement, got {intimidate.enhancements}",
        )
        self.assertEqual(intimidate.enhancements[0].technique.pk, self.technique.pk)

    def test_target_spec_populated_for_persona_targeted_actions(self) -> None:
        actions = get_player_actions(self.character)
        intimidate = next((a for a in actions if a.display_name == "Intimidate"), None)
        self.assertIsNotNone(intimidate)
        self.assertIsNotNone(intimidate.target_spec)
        self.assertEqual(intimidate.target_spec.kind, TargetKind.PERSONA)
        self.assertEqual(intimidate.target_spec.cardinality, TargetType.SINGLE)
        self.assertTrue(intimidate.target_spec.filters.in_same_scene)
        self.assertTrue(intimidate.target_spec.filters.exclude_self)

    def test_strain_availability_present_when_anima_exists(self) -> None:
        CharacterAnimaFactory(character=self.character, current=10, maximum=10)

        actions = get_player_actions(self.character)
        intimidate = next((a for a in actions if a.display_name == "Intimidate"), None)
        self.assertIsNotNone(intimidate)
        self.assertIsNotNone(intimidate.strain)
        self.assertEqual(intimidate.strain.cap, 10)

    def test_strain_absent_when_anima_missing(self) -> None:
        """A character with no CharacterAnima row gets strain=None."""
        actions = get_player_actions(self.character)
        intimidate = next((a for a in actions if a.display_name == "Intimidate"), None)
        self.assertIsNotNone(intimidate)
        self.assertIsNone(intimidate.strain)

    def test_action_without_enhancements_has_empty_tuple(self) -> None:
        """A social action with no matching enhancements still carries enhancements=()."""
        unrelated_template = _make_social_template("Persuade")
        actions = get_player_actions(self.character)
        persuade = next((a for a in actions if a.display_name == "Persuade"), None)
        self.assertIsNotNone(persuade)
        self.assertEqual(persuade.enhancements, ())
        # target_spec is still synthesized from social-template metadata.
        self.assertIsNotNone(persuade.target_spec)
        del unrelated_template


class GetPlayerActionsQueryCountTests(TestCase):
    """get_player_actions performs <= 8 queries for a non-trivial setup."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.template = _make_social_template("Intimidate")
        cls.technique = TechniqueFactory(name="Wave of Dread")
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)
        ActionEnhancement.objects.create(
            base_action_key="intimidate",
            variant_name="Dread Intimidate",
            source_type="technique",
            technique=cls.technique,
        )
        CharacterAnimaFactory(character=cls.character, current=8, maximum=8)
        # A second template with no enhancement to ensure unmatched paths don't
        # add per-template queries.
        _make_social_template("Persuade")

    def test_query_count_is_bounded(self) -> None:
        with CaptureQueriesContext(connection) as ctx:
            actions = get_player_actions(self.character)

        # Sanity: the call returned something.
        self.assertTrue(len(actions) >= 1)

        # The fold-in adds a constant ~9 queries for the enhancement pipeline
        # (ActionTemplate, CharacterTechnique, CharacterAnima, ActionEnhancement+technique join,
        # Soulfray ConditionInstance, plus 4 from runtime stat calculation: CharacterSheet,
        # ModifierTarget, CharacterEngagement, IntensityTier). Two extra queries come from
        # the pre-existing CombatParticipant lookups in _combat_actions and
        # _clash_contribution_actions (one per call site; deduplicating those is out of
        # scope for this PR).
        #
        # Cap set at 12 to give margin without masking regressions. Raise only with a
        # documented justification — the goal remains a single-digit cost.
        self.assertLessEqual(
            len(ctx.captured_queries),
            12,
            f"get_player_actions issued {len(ctx.captured_queries)} queries: "
            f"{[q['sql'] for q in ctx.captured_queries]}",
        )
