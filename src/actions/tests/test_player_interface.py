"""Tests for PlayerAction/ActionRef descriptor types and ActionBackend enum."""

from django.test import TestCase

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.types import ActionRef, PlayerAction
from world.checks.factories import CheckTypeFactory
from world.mechanics.constants import DifficultyIndicator


class ActionBackendTest(TestCase):
    """ActionBackend enum has the expected values."""

    def test_backend_values(self) -> None:
        self.assertEqual(ActionBackend.CHALLENGE, "challenge")
        self.assertEqual(ActionBackend.COMBAT, "combat")
        self.assertEqual(ActionBackend.REGISTRY, "registry")


class PlayerActionChallengeTest(TestCase):
    """CHALLENGE-backed PlayerAction: no action_template (plain check_type-direct case)."""

    def test_challenge_backend_no_template(self) -> None:
        check_type = CheckTypeFactory()
        ref = ActionRef(
            backend=ActionBackend.CHALLENGE,
            challenge_instance_id=10,
            approach_id=5,
        )
        action = PlayerAction(
            backend=ActionBackend.CHALLENGE,
            check_type=check_type,
            display_name="Flame Lance",
            ref=ref,
        )

        # backend correct
        self.assertEqual(action.backend, ActionBackend.CHALLENGE)
        # action_template defaults to None for plain challenge approaches
        self.assertIsNone(action.action_template)
        # check_type is the SAME instance (not a copy or pk)
        self.assertIs(action.check_type, check_type)
        # ref round-trip
        self.assertEqual(action.ref.backend, ActionBackend.CHALLENGE)
        self.assertEqual(action.ref.challenge_instance_id, 10)
        self.assertEqual(action.ref.approach_id, 5)
        self.assertIsNone(action.ref.technique_id)
        self.assertIsNone(action.ref.registry_key)


class PlayerActionRegistryTest(TestCase):
    """REGISTRY-backed PlayerAction carries registry_key in ref."""

    def test_registry_ref_fields(self) -> None:
        check_type = CheckTypeFactory()
        template = ActionTemplateFactory()
        ref = ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key="intimidate",
        )
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            check_type=check_type,
            display_name="Intimidate",
            ref=ref,
            action_template=template,
        )
        self.assertEqual(action.backend, ActionBackend.REGISTRY)
        self.assertEqual(action.ref.registry_key, "intimidate")
        self.assertIsNone(action.ref.challenge_instance_id)
        self.assertIsNone(action.ref.technique_id)
        self.assertIs(action.action_template, template)
        self.assertIs(action.check_type, check_type)


class PlayerActionCombatTest(TestCase):
    """COMBAT-backed PlayerAction carries technique_id in ref."""

    def test_combat_ref_fields(self) -> None:
        check_type = CheckTypeFactory()
        template = ActionTemplateFactory()
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            technique_id=99,
        )
        action = PlayerAction(
            backend=ActionBackend.COMBAT,
            check_type=check_type,
            display_name="Searing Bolt",
            ref=ref,
            action_template=template,
        )
        self.assertEqual(action.backend, ActionBackend.COMBAT)
        self.assertEqual(action.ref.technique_id, 99)
        self.assertIsNone(action.ref.registry_key)
        self.assertIsNone(action.ref.challenge_instance_id)
        self.assertIs(action.action_template, template)
        self.assertIs(action.check_type, check_type)


class PlayerActionDefaultsTest(TestCase):
    """PlayerAction has correct defaults for optional fields."""

    def test_defaults(self) -> None:
        check_type = CheckTypeFactory()
        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="look")
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            check_type=check_type,
            display_name="Look",
            ref=ref,
        )
        self.assertIsNone(action.action_template)
        self.assertEqual(action.description, "")
        self.assertIsNone(action.difficulty)
        self.assertTrue(action.prerequisite_met)
        self.assertEqual(action.prerequisite_reasons, [])

    def test_difficulty_indicator(self) -> None:
        check_type = CheckTypeFactory()
        ref = ActionRef(backend=ActionBackend.CHALLENGE, challenge_instance_id=1)
        action = PlayerAction(
            backend=ActionBackend.CHALLENGE,
            check_type=check_type,
            display_name="Hard Fight",
            ref=ref,
            difficulty=DifficultyIndicator.HARD,
        )
        self.assertEqual(action.difficulty, DifficultyIndicator.HARD)
