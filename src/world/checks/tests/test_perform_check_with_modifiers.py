"""Tests for perform_check_with_modifiers() — the sheet-resolving wrapper.

Verifies that the helper resolves CharacterSheet, guards None for sheet-less
actors, calls collect_check_modifiers, and forwards breakdown.total
additively to perform_check.
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.services import perform_check_with_modifiers


class PerformCheckWithModifiersTest(TestCase):
    """Tests for the perform_check_with_modifiers wrapper."""

    @classmethod
    def setUpTestData(cls):
        cls.check_type = CheckTypeFactory(name="wrapper-test-check")

    def setUp(self):
        self.target = ObjectDBFactory(db_key="WrapperTarget")
        self.sheet = CharacterSheetFactory(character=self.target)

    def test_sheet_present_calls_aggregator_and_adds_total(self):
        """When sheet exists, collect_check_modifiers is called and its total
        is added to extra_modifiers before forwarding to perform_check."""
        with (
            patch("world.checks.services.collect_check_modifiers") as mock_collect,
            patch("world.checks.services.perform_check") as mock_perform,
        ):
            mock_collect.return_value.total = 5
            perform_check_with_modifiers(
                self.target,
                self.check_type,
                target_difficulty=10,
                extra_modifiers=3,
            )
            # Aggregator was called with the sheet and check_type.
            mock_collect.assert_called_once_with(self.sheet, self.check_type, scene=None)
            # perform_check received extra_modifiers=3+5=8.
            call_kwargs = mock_perform.call_args
            assert call_kwargs.kwargs["extra_modifiers"] == 8

    def test_sheet_none_forwards_without_aggregator(self):
        """When character has no sheet (sheet-less actor), forward to
        perform_check with extra_modifiers unchanged; do NOT call the
        aggregator."""
        sheetless = ObjectDBFactory(db_key="SheetlessNPC")
        # Ensure no CharacterSheet exists for this object.
        from world.character_sheets.models import CharacterSheet

        CharacterSheet.objects.filter(character=sheetless).delete()

        with (
            patch("world.checks.services.collect_check_modifiers") as mock_collect,
            patch("world.checks.services.perform_check") as mock_perform,
        ):
            perform_check_with_modifiers(
                sheetless,
                self.check_type,
                target_difficulty=5,
                extra_modifiers=7,
            )
            mock_collect.assert_not_called()
            call_kwargs = mock_perform.call_args
            assert call_kwargs.kwargs["extra_modifiers"] == 7

    def test_scene_passed_to_aggregator(self):
        """When scene= is supplied, it reaches collect_check_modifiers."""
        from world.scenes.factories import SceneFactory

        scene = SceneFactory()
        with (
            patch("world.checks.services.collect_check_modifiers") as mock_collect,
            patch("world.checks.services.perform_check"),
        ):
            mock_collect.return_value.total = 0
            perform_check_with_modifiers(self.target, self.check_type, scene=scene)
            mock_collect.assert_called_once_with(self.sheet, self.check_type, scene=scene)

    def test_all_params_forwarded(self):
        """specialization, situation_ctx, effort_level, fatigue_penalty,
        and level_override all reach perform_check unchanged."""
        from world.skills.factories import SpecializationFactory

        spec = SpecializationFactory()
        with (
            patch("world.checks.services.collect_check_modifiers") as mock_collect,
            patch("world.checks.services.perform_check") as mock_perform,
        ):
            mock_collect.return_value.total = 0
            perform_check_with_modifiers(
                self.target,
                self.check_type,
                target_difficulty=10,
                extra_modifiers=2,
                effort_level="STANDARD",
                fatigue_penalty=-1,
                specialization=spec,
                situation_ctx=None,
                level_override=5,
            )
            call = mock_perform.call_args
            assert call.kwargs["target_difficulty"] == 10
            assert call.kwargs["effort_level"] == "STANDARD"
            assert call.kwargs["fatigue_penalty"] == -1
            assert call.kwargs["specialization"] == spec
            assert call.kwargs["level_override"] == 5
