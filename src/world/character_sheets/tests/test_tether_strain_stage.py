"""Tests for CharacterSheet.get_tether_strain_stage (Phase 6 / Task 7)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionInstanceFactory
from world.magic.factories import TetherStrainTemplateFactory


class TestGetTetherStrainStage(TestCase):
    """CharacterSheet.get_tether_strain_stage() returns 0 or the current stage_order."""

    def test_returns_zero_when_no_instance(self) -> None:
        sheet = CharacterSheetFactory()
        self.assertEqual(sheet.get_tether_strain_stage(), 0)

    def test_returns_stage_when_instance_exists(self) -> None:
        sheet = CharacterSheetFactory()
        template = TetherStrainTemplateFactory()
        # TetherStrainTemplateFactory wires 5 stages via post_generation; fetch stage 2.
        stage = template.stages.get(stage_order=2)
        ConditionInstanceFactory(
            target=sheet.character,
            condition=template,
            current_stage=stage,
        )
        self.assertEqual(sheet.get_tether_strain_stage(), 2)

    def test_returns_zero_when_instance_has_no_current_stage(self) -> None:
        sheet = CharacterSheetFactory()
        template = TetherStrainTemplateFactory()
        ConditionInstanceFactory(
            target=sheet.character,
            condition=template,
            current_stage=None,
        )
        self.assertEqual(sheet.get_tether_strain_stage(), 0)

    def test_returns_stage_5_at_terminal(self) -> None:
        sheet = CharacterSheetFactory()
        template = TetherStrainTemplateFactory()
        stage = template.stages.get(stage_order=5)
        ConditionInstanceFactory(
            target=sheet.character,
            condition=template,
            current_stage=stage,
        )
        self.assertEqual(sheet.get_tether_strain_stage(), 5)
