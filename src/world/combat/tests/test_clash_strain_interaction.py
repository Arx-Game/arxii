"""Tests that commit_to_clash records strain_committed on the resulting Interaction."""

from __future__ import annotations

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.clash import commit_to_clash
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatParticipantFactory,
    StrainConfigFactory,
)
from world.magic.factories import CharacterAnimaFactory, TechniqueFactory
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction
from world.traits.factories import CheckOutcomeFactory


class ClashStrainInteractionTests(TestCase):
    """The Interaction created at clash resolution records strain_committed."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config_strain = StrainConfigFactory()
        cls.config_clash = ClashConfigFactory()
        cls.check_type = ActionTemplateFactory().check_type
        cls.success_outcome = CheckOutcomeFactory(name="strain_success", success_level=1)

    def _make_setup(self, anima_current: int = 20) -> tuple[object, object, object]:
        """Build the minimum CombatParticipant + technique + clash for a commit."""
        sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=sheet.character, current=anima_current, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        clash = ClashFactory()
        # The participant must live in the same encounter as the clash so
        # commit_to_clash's lookup resolves it.
        CombatParticipantFactory(encounter=clash.encounter, character_sheet=sheet)
        template = ActionTemplateFactory(check_type=self.check_type)
        technique = TechniqueFactory(
            intensity=5, control=10, anima_cost=3, action_template=template
        )
        return sheet, clash, technique

    def test_interaction_records_clash_strain(self) -> None:
        """A non-zero strain commitment lands on the created Interaction row."""
        sheet, clash, technique = self._make_setup()

        before = Interaction.objects.count()
        with force_check_outcome(self.success_outcome):
            commit_to_clash(
                character_sheet=sheet,
                technique=technique,
                clash=clash,
                strain_commitment=5,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        # commit_to_clash should have written exactly one ACTION-mode Interaction.
        new_interactions = Interaction.objects.filter(mode=InteractionMode.ACTION)
        self.assertEqual(new_interactions.count(), before + 1)
        latest = new_interactions.latest("timestamp")
        self.assertEqual(latest.strain_committed, 5)

    def test_zero_strain_persisted_as_zero(self) -> None:
        sheet, clash, technique = self._make_setup()

        with force_check_outcome(self.success_outcome):
            commit_to_clash(
                character_sheet=sheet,
                technique=technique,
                clash=clash,
                strain_commitment=0,
                action_slot="FOCUSED",
                config_clash=self.config_clash,
                config_strain=self.config_strain,
            )

        latest = Interaction.objects.filter(mode=InteractionMode.ACTION).latest("timestamp")
        self.assertEqual(latest.strain_committed, 0)
