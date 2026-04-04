"""End-to-end pipeline tests for social actions.

These tests serve two purposes:
  1. Automated regression coverage for the social action pipeline.
  2. Seed data generation — running the test suite populates the dev DB with
     realistic social action content via FactoryBoy.

Test structure:
  SocialActionAvailabilityTests — get_available_scene_actions returns social templates
  SocialActionConsentFlowTests  — ACCEPT/DENY consent flow mechanics
  SocialActionConsequenceTests  — full resolution: condition applied to TARGET
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from integration_tests.game_content.characters import CharacterContent
from integration_tests.game_content.checks import CheckContent
from integration_tests.game_content.social import ACTION_CONDITION_MAP, SocialContent
from world.conditions.services import has_condition
from world.scenes.action_availability import get_available_scene_actions
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import SceneFactory


class SocialActionAvailabilityTests(TestCase):
    """get_available_scene_actions returns the 6 wired social actions."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.action_templates = CheckContent.create_action_templates()
        cls.character, cls.persona = CharacterContent.create_base_social_character(name="Aria")

    def test_returns_six_social_actions(self) -> None:
        actions = get_available_scene_actions(character=self.character)
        assert len(actions) == 6

    def test_action_keys_match_template_names(self) -> None:
        actions = get_available_scene_actions(character=self.character)
        keys = {a.action_key for a in actions}
        expected = {"intimidate", "persuade", "deceive", "flirt", "perform", "entrance"}
        assert keys == expected

    def test_no_enhancements_without_techniques(self) -> None:
        """Baseline: no technique enhancements for a character with no techniques."""
        actions = get_available_scene_actions(character=self.character)
        for action in actions:
            assert action.enhancements == []


class SocialActionConsentFlowTests(TestCase):
    """Consent flow: PENDING → ACCEPTED or DENIED."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator_char, cls.initiator_persona = CharacterContent.create_base_social_character(
            name="Bastian"
        )
        cls.target_char, cls.target_persona = CharacterContent.create_base_social_character(
            name="Lisette"
        )

    def test_create_request_is_pending(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="intimidate",
        )
        assert request.status == ActionRequestStatus.PENDING
        assert request.action_key == "intimidate"

    def test_deny_marks_request_denied(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="persuade",
        )
        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.DENY,
        )
        assert result is None
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.DENIED

    def test_respond_to_already_resolved_request_returns_none(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="flirt",
        )
        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.DENY,
        )
        # Second response — request is no longer PENDING
        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.DENY,
        )
        assert result is None


class SocialActionConsequenceTests(TestCase):
    """Full pipeline: accepted action applies condition to TARGET on success."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.content = SocialContent.create_all()
        cls.scene = SceneFactory()
        cls.initiator_char, cls.initiator_persona = CharacterContent.create_base_social_character(
            name="Evander"
        )
        cls.target_char, cls.target_persona = CharacterContent.create_base_social_character(
            name="Sable"
        )

    def _accept_action(self, action_key: str) -> None:
        """Create and accept an action request for the given action_key."""
        template = self.content.templates[action_key]
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key=action_key,
        )
        request.action_template = template
        request.save(update_fields=["action_template"])
        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

    def test_successful_intimidate_applies_shaken_to_target(self) -> None:
        """A successful Intimidate applies Shaken to the TARGET, not the initiator."""
        condition = self.content.conditions["Shaken"]
        # Roll 90 → Success on the diff=1 chart (Success: 86-100)
        # Character has 75 trait pts (presence 50 + strength 25) → rank 2;
        # NORMAL difficulty 45 pts → rank 1; rank_diff=1; Hard chart: success 86-100.
        with patch("world.checks.services.random.randint", return_value=90):
            self._accept_action("intimidate")

        assert has_condition(self.target_char, condition), "Target should have Shaken"
        assert not has_condition(self.initiator_char, condition), "Initiator should not have Shaken"

    def test_successful_persuade_applies_charmed_to_target(self) -> None:
        condition = self.content.conditions["Charmed"]
        with patch("world.checks.services.random.randint", return_value=90):
            self._accept_action("persuade")

        assert has_condition(self.target_char, condition)
        assert not has_condition(self.initiator_char, condition)

    def test_failure_does_not_apply_condition(self) -> None:
        """A failed Intimidate (roll 20 → Failure) applies no condition."""
        condition = self.content.conditions["Shaken"]
        # Roll 20 → Failure on diff=1 chart (Failure: 1-70)
        with patch("world.checks.services.random.randint", return_value=20):
            self._accept_action("intimidate")

        assert not has_condition(self.target_char, condition)
        assert not has_condition(self.initiator_char, condition)

    def test_all_six_actions_have_condition_mapping(self) -> None:
        """Every social action key has a corresponding condition in the content."""
        for action_key in ACTION_CONDITION_MAP:
            assert action_key in self.content.templates, f"Missing template for {action_key}"
            condition_name = ACTION_CONDITION_MAP[action_key]
            assert condition_name in self.content.conditions, f"Missing condition {condition_name}"
