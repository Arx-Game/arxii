"""Tests for ambient relationship bumps (#1699): models, service, seeds."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.relationships.constants import BumpValence, TrackSign, TrackSystemKey
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipBumpFactory,
    RelationshipTrackFactory,
)
from world.relationships.models import RelationshipBump, RelationshipTrack
from world.scenes.factories import InteractionFactory


class RelationshipBumpModelTests(TestCase):
    """Model-level constraints for RelationshipBump and system tracks."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.relationship = CharacterRelationshipFactory()
        cls.interaction = InteractionFactory()

    def test_duplicate_bump_per_interaction_rejected(self) -> None:
        RelationshipBumpFactory(relationship=self.relationship, interaction=self.interaction)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            RelationshipBumpFactory(
                relationship=self.relationship,
                interaction=self.interaction,
                valence=BumpValence.NEGATIVE,
            )

    def test_same_interaction_bumpable_by_other_relationship(self) -> None:
        RelationshipBumpFactory(relationship=self.relationship, interaction=self.interaction)
        other = CharacterRelationshipFactory()
        bump = RelationshipBumpFactory(relationship=other, interaction=self.interaction)
        self.assertEqual(RelationshipBump.objects.filter(interaction=self.interaction).count(), 2)
        self.assertEqual(bump.timestamp, self.interaction.timestamp)

    def test_system_key_unique(self) -> None:
        RelationshipTrackFactory(name="Regard", system_key=TrackSystemKey.REGARD)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            RelationshipTrack.objects.create(
                name="Regard2",
                slug="regard2",
                sign=TrackSign.POSITIVE,
                system_key=TrackSystemKey.REGARD,
            )

    def test_system_key_nullable_for_authored_tracks(self) -> None:
        a = RelationshipTrackFactory(name="Friendship")
        b = RelationshipTrackFactory(name="Rivalry", sign=TrackSign.NEGATIVE)
        self.assertIsNone(a.system_key)
        self.assertIsNone(b.system_key)
