"""Tests that SceneActionRequestSerializer (consent prompt) exposes strain_commitment."""

from django.test import TestCase

from world.scenes.action_serializers import SceneActionRequestSerializer
from world.scenes.factories import SceneActionRequestFactory


class SceneActionRequestSerializerStrainTests(TestCase):
    """The GET serializer for SceneActionRequest exposes strain_commitment."""

    def test_serializer_includes_strain_commitment(self) -> None:
        request = SceneActionRequestFactory(strain_commitment=3)
        data = SceneActionRequestSerializer(request).data
        self.assertEqual(data["strain_commitment"], 3)

    def test_serializer_strain_commitment_defaults_zero(self) -> None:
        request = SceneActionRequestFactory()
        data = SceneActionRequestSerializer(request).data
        self.assertEqual(data["strain_commitment"], 0)
