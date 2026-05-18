"""Tests for PlayerAction/ActionRef descriptor types and ActionBackend enum."""

from django.test import TestCase

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.types import ActionRef, PlayerAction
from world.mechanics.constants import CapabilitySourceType, DifficultyIndicator
from world.mechanics.types import CapabilitySource


class ActionBackendTest(TestCase):
    """ActionBackend enum has the expected values."""

    def test_backend_values(self) -> None:
        self.assertEqual(ActionBackend.CHALLENGE, "challenge")
        self.assertEqual(ActionBackend.COMBAT, "combat")
        self.assertEqual(ActionBackend.REGISTRY, "registry")


class PlayerActionChallengeTest(TestCase):
    """Construct a CHALLENGE-backed PlayerAction and verify ref round-trip."""

    def test_challenge_backend_and_instance_identity(self) -> None:
        template = ActionTemplateFactory()
        capability_source = CapabilitySource(
            capability_name="generation",
            capability_id=1,
            value=3,
            source_type=CapabilitySourceType.TECHNIQUE,
            source_name="Flame Lance",
            source_id=42,
        )
        ref = ActionRef(
            backend=ActionBackend.CHALLENGE,
            challenge_instance_id=10,
            approach_id=5,
        )
        action = PlayerAction(
            backend=ActionBackend.CHALLENGE,
            action_template=template,
            display_name="Flame Lance",
            ref=ref,
        )

        # backend correct
        self.assertEqual(action.backend, ActionBackend.CHALLENGE)
        # action_template is the SAME instance (not a copy or pk)
        self.assertIs(action.action_template, template)
        # ref round-trip
        self.assertEqual(action.ref.backend, ActionBackend.CHALLENGE)
        self.assertEqual(action.ref.challenge_instance_id, 10)
        self.assertEqual(action.ref.approach_id, 5)
        self.assertIsNone(action.ref.technique_id)
        self.assertIsNone(action.ref.registry_key)

        # capability_source was used to build the action — confirm it's reachable
        # (this field is not on PlayerAction per spec — just verify it's valid)
        self.assertEqual(capability_source.capability_name, "generation")


class PlayerActionRegistryTest(TestCase):
    """REGISTRY-backed PlayerAction carries registry_key in ref."""

    def test_registry_ref_fields(self) -> None:
        template = ActionTemplateFactory()
        ref = ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key="intimidate",
        )
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            action_template=template,
            display_name="Intimidate",
            ref=ref,
        )
        self.assertEqual(action.backend, ActionBackend.REGISTRY)
        self.assertEqual(action.ref.registry_key, "intimidate")
        self.assertIsNone(action.ref.challenge_instance_id)
        self.assertIsNone(action.ref.technique_id)


class PlayerActionCombatTest(TestCase):
    """COMBAT-backed PlayerAction carries technique_id in ref."""

    def test_combat_ref_fields(self) -> None:
        template = ActionTemplateFactory()
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            technique_id=99,
        )
        action = PlayerAction(
            backend=ActionBackend.COMBAT,
            action_template=template,
            display_name="Searing Bolt",
            ref=ref,
        )
        self.assertEqual(action.backend, ActionBackend.COMBAT)
        self.assertEqual(action.ref.technique_id, 99)
        self.assertIsNone(action.ref.registry_key)
        self.assertIsNone(action.ref.challenge_instance_id)


class PlayerActionDefaultsTest(TestCase):
    """PlayerAction has correct defaults for optional fields."""

    def test_defaults(self) -> None:
        template = ActionTemplateFactory()
        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="look")
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            action_template=template,
            display_name="Look",
            ref=ref,
        )
        self.assertEqual(action.description, "")
        self.assertIsNone(action.difficulty)
        self.assertTrue(action.prerequisite_met)
        self.assertEqual(action.prerequisite_reasons, [])

    def test_difficulty_indicator(self) -> None:
        template = ActionTemplateFactory()
        ref = ActionRef(backend=ActionBackend.CHALLENGE, challenge_instance_id=1)
        action = PlayerAction(
            backend=ActionBackend.CHALLENGE,
            action_template=template,
            display_name="Hard Fight",
            ref=ref,
            difficulty=DifficultyIndicator.HARD,
        )
        self.assertEqual(action.difficulty, DifficultyIndicator.HARD)
