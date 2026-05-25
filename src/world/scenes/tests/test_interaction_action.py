"""Smoke tests for the InteractionAction bridge model."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.scenes.constants import InteractionMode
from world.scenes.factories import InteractionActionFactory, InteractionFactory
from world.scenes.models import InteractionAction


class InteractionActionModelTests(TestCase):
    def test_bridge_links_pose_and_action(self) -> None:
        link = InteractionActionFactory()
        self.assertEqual(link.pose.mode, InteractionMode.POSE)
        self.assertEqual(link.action_interaction.mode, InteractionMode.ACTION)

    def test_clean_rejects_pose_with_wrong_mode(self) -> None:
        # SAY-mode Interaction in the pose slot must be rejected.
        pose = InteractionFactory(mode=InteractionMode.SAY)
        action = InteractionFactory(mode=InteractionMode.ACTION)
        link = InteractionAction(pose=pose, action_interaction=action)
        with self.assertRaises(ValidationError) as ctx:
            link.clean()
        self.assertIn("pose", ctx.exception.error_dict)

    def test_clean_rejects_action_interaction_with_wrong_mode(self) -> None:
        # POSE-mode Interaction in the action_interaction slot must be rejected.
        pose = InteractionFactory(mode=InteractionMode.POSE)
        action = InteractionFactory(mode=InteractionMode.POSE)
        link = InteractionAction(pose=pose, action_interaction=action)
        with self.assertRaises(ValidationError) as ctx:
            link.clean()
        self.assertIn("action_interaction", ctx.exception.error_dict)

    def test_unique_per_pose_action(self) -> None:
        link = InteractionActionFactory()
        # Wrap the second insert in a savepoint so the TestCase outer transaction
        # survives the IntegrityError.
        with self.assertRaises(IntegrityError), transaction.atomic():
            InteractionActionFactory(
                pose=link.pose,
                action_interaction=link.action_interaction,
            )
