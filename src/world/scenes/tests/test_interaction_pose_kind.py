"""Tests for Spec C Interaction.pose_kind field."""

from django.test import TestCase

from world.scenes.factories import InteractionFactory


class InteractionPoseKindTests(TestCase):
    def test_default_is_standard(self) -> None:
        from world.scenes.constants import PoseKind

        interaction = InteractionFactory()
        self.assertEqual(interaction.pose_kind, PoseKind.STANDARD)

    def test_entry_value(self) -> None:
        from world.scenes.constants import PoseKind

        interaction = InteractionFactory(pose_kind=PoseKind.ENTRY)
        interaction.refresh_from_db()
        self.assertEqual(interaction.pose_kind, PoseKind.ENTRY)

    def test_departure_value(self) -> None:
        from world.scenes.constants import PoseKind

        interaction = InteractionFactory(pose_kind=PoseKind.DEPARTURE)
        interaction.refresh_from_db()
        self.assertEqual(interaction.pose_kind, PoseKind.DEPARTURE)
