"""Tests that create_action_request accepts and persists strain_commitment."""

from django.test import TestCase

from world.magic.factories import CharacterAnimaFactory
from world.scenes.action_services import create_action_request
from world.scenes.factories import PersonaFactory, SceneFactory


class CreateActionRequestStrainTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        CharacterAnimaFactory(character=cls.initiator.character_sheet, current=3, maximum=3)
        cls.target = PersonaFactory()

    def test_strain_commitment_persisted_on_request(self) -> None:
        CharacterAnimaFactory(
            character=self.initiator.character_sheet,
            current=3,
            maximum=3,
        )
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
            strain_commitment=3,
        )
        self.assertEqual(request.strain_commitment, 3)

    def test_strain_defaults_to_zero(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        self.assertEqual(request.strain_commitment, 0)
