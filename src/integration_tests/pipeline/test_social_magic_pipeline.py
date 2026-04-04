"""End-to-end pipeline tests for technique-enhanced social actions.

Test structure:
  SocialMagicAvailabilityTests   — technique-enhanced actions appear in available actions
  SocialMagicConsequenceTests    — full pipeline: anima deducted, condition on target
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from integration_tests.game_content.characters import CharacterContent
from integration_tests.game_content.magic import ACTION_TECHNIQUE_MAP, MagicContent
from integration_tests.game_content.social import SocialContent
from world.conditions.services import has_condition
from world.scenes.action_availability import get_available_scene_actions
from world.scenes.action_constants import ConsentDecision
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import SceneFactory


class SocialMagicAvailabilityTests(TestCase):
    """Character with known techniques sees them in get_available_scene_actions."""

    @classmethod
    def setUpTestData(cls) -> None:
        from integration_tests.game_content.checks import CheckContent

        CheckContent.create_action_templates()
        cls.magic = MagicContent.create_all()
        cls.initiator_char, cls.initiator_persona = CharacterContent.create_base_social_character(
            name="Mira"
        )
        cls.other_char, cls.other_persona = CharacterContent.create_base_social_character(
            name="Fen"
        )
        # Mira knows all 6 techniques; Fen knows none
        MagicContent.grant_techniques_to_character(
            cls.initiator_char, list(cls.magic.techniques.values())
        )

    def test_known_techniques_appear_as_enhancements(self) -> None:
        actions = get_available_scene_actions(character=self.initiator_char)
        actions_by_key = {a.action_key: a for a in actions}
        for action_key in ACTION_TECHNIQUE_MAP:
            assert actions_by_key[action_key].enhancements, f"Expected enhancement on {action_key}"

    def test_enhancement_links_correct_technique(self) -> None:
        actions = get_available_scene_actions(character=self.initiator_char)
        actions_by_key = {a.action_key: a for a in actions}
        intimidate = actions_by_key["intimidate"]
        assert intimidate.enhancements[0].technique == self.magic.techniques["intimidate"]

    def test_character_without_techniques_has_no_enhancements(self) -> None:
        actions = get_available_scene_actions(character=self.other_char)
        for action in actions:
            assert action.enhancements == []


class SocialMagicConsequenceTests(TestCase):
    """Full pipeline: technique-enhanced action deducts anima and applies condition to target."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.content = SocialContent.create_all()
        cls.magic = MagicContent.create_all()
        cls.scene = SceneFactory()
        cls.initiator_char, cls.initiator_persona = CharacterContent.create_base_social_character(
            name="Corvus"
        )
        cls.target_char, cls.target_persona = CharacterContent.create_base_social_character(
            name="Wren"
        )
        MagicContent.grant_techniques_to_character(
            cls.initiator_char, list(cls.magic.techniques.values())
        )

    def _accept_enhanced_action(self, action_key: str) -> None:
        """Create and accept a technique-enhanced action request."""
        template = self.content.templates[action_key]
        technique = self.magic.techniques[action_key]
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key=action_key,
            technique=technique,
        )
        request.action_template = template
        request.save(update_fields=["action_template"])
        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

    def test_enhanced_intimidate_applies_shaken_to_target(self) -> None:
        """Technique-enhanced Intimidate applies Shaken to TARGET, not initiator."""
        condition = self.content.conditions["Shaken"]
        # Roll 90 → Success on diff=1 chart (Success: 86-100)
        with patch("world.checks.services.random.randint", return_value=90):
            self._accept_enhanced_action("intimidate")

        assert has_condition(self.target_char, condition), "Target should have Shaken"
        assert not has_condition(self.initiator_char, condition), "Initiator should not have Shaken"

    def test_enhanced_action_deducts_anima_from_initiator(self) -> None:
        """Technique use deducts anima from the initiator's pool."""
        anima_before = self.initiator_char.anima.current
        with patch("world.checks.services.random.randint", return_value=90):
            self._accept_enhanced_action("persuade")

        self.initiator_char.anima.refresh_from_db()
        assert self.initiator_char.anima.current < anima_before

    def test_enhanced_action_result_has_technique_result(self) -> None:
        """respond_to_action_request returns EnhancedSceneActionResult with technique_result."""
        template = self.content.templates["flirt"]
        technique = self.magic.techniques["flirt"]
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="flirt",
            technique=technique,
        )
        request.action_template = template
        request.save(update_fields=["action_template"])
        with patch("world.checks.services.random.randint", return_value=90):
            result = respond_to_action_request(
                action_request=request,
                decision=ConsentDecision.ACCEPT,
            )

        assert result is not None
        assert result.technique_result is not None
        assert result.technique_result.anima_cost.effective_cost >= 0
