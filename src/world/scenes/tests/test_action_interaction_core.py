from __future__ import annotations

from django.test import TestCase

from world.scenes.constants import InteractionMode
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.interaction_services import create_action_interaction_core


class CreateActionInteractionCoreTests(TestCase):
    def test_creates_action_mode_interaction(self) -> None:
        scene = SceneFactory()
        persona = PersonaFactory()
        interaction = create_action_interaction_core(
            persona=persona, scene=scene, summary_label="Frost Bolt", strain_committed=2
        )
        assert interaction.mode == InteractionMode.ACTION
        assert interaction.persona_id == persona.pk
        assert interaction.scene_id == scene.pk
        assert interaction.content == "Frost Bolt"
        assert interaction.strain_committed == 2
