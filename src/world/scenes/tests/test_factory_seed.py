"""Seed-data tests confirming SceneActionRequestFactory exposes strain_commitment.

Factories double as integration-test setUp AND new-player/staff seed data, so
``strain_commitment`` must be a configurable factory attribute (defaults to 0
when omitted, accepts any non-negative override).
"""

from django.test import TestCase

from world.scenes.action_constants import ActionRequestStatus
from world.scenes.factories import SceneActionRequestFactory


class SceneActionRequestFactorySeedTests(TestCase):
    """SceneActionRequestFactory accepts strain_commitment and seeds full chain."""

    def test_factory_creates_request_with_strain(self) -> None:
        request = SceneActionRequestFactory(strain_commitment=4)
        self.assertEqual(request.strain_commitment, 4)

    def test_factory_default_strain_is_zero(self) -> None:
        request = SceneActionRequestFactory()
        self.assertEqual(request.strain_commitment, 0)

    def test_factory_chain_seeds_full_scene_with_pending_request(self) -> None:
        request = SceneActionRequestFactory(strain_commitment=2)
        self.assertIsNotNone(request.scene)
        self.assertIsNotNone(request.initiator_persona)
        self.assertIsNotNone(request.target_persona)
        self.assertEqual(request.status, ActionRequestStatus.PENDING)
