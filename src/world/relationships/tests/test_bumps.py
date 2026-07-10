"""Tests for ambient relationship bumps (#1699): models, service, seeds."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import BUMP_POINTS, BumpValence, TrackSign, TrackSystemKey
from world.relationships.exceptions import AlreadyAcknowledgedError, SystemTracksNotSeededError
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipBumpFactory,
    RelationshipTrackFactory,
)
from world.relationships.models import (
    CharacterRelationship,
    RelationshipBump,
    RelationshipTrack,
    RelationshipTrackProgress,
)
from world.relationships.services import apply_relationship_bump
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


class ApplyRelationshipBumpTests(TestCase):
    """Service-level behavior of apply_relationship_bump."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.regard = RelationshipTrackFactory(
            name="Regard", sign=TrackSign.POSITIVE, system_key=TrackSystemKey.REGARD
        )
        cls.friction = RelationshipTrackFactory(
            name="Friction", sign=TrackSign.NEGATIVE, system_key=TrackSystemKey.FRICTION
        )
        cls.source = CharacterSheetFactory()
        cls.target = CharacterSheetFactory()
        cls.interaction = InteractionFactory()

    def test_positive_bump_lands_on_regard(self) -> None:
        bump = apply_relationship_bump(
            source=self.source,
            target=self.target,
            interaction=self.interaction,
            valence=1,
        )
        self.assertEqual(bump.valence, BumpValence.POSITIVE)
        relationship = CharacterRelationship.objects.get(source=self.source, target=self.target)
        self.assertTrue(relationship.is_pending)
        progress = RelationshipTrackProgress.objects.get(
            relationship=relationship, track=self.regard
        )
        self.assertEqual(progress.developed_points, BUMP_POINTS)
        self.assertEqual(progress.capacity, BUMP_POINTS)
        self.assertEqual(relationship.affection, BUMP_POINTS)

    def test_negative_bump_lands_on_friction_and_cools_affection(self) -> None:
        apply_relationship_bump(
            source=self.source,
            target=self.target,
            interaction=self.interaction,
            valence=-1,
        )
        relationship = CharacterRelationship.objects.get(source=self.source, target=self.target)
        progress = RelationshipTrackProgress.objects.get(
            relationship=relationship, track=self.friction
        )
        self.assertEqual(progress.developed_points, BUMP_POINTS)
        self.assertEqual(relationship.affection, -BUMP_POINTS)

    def test_duplicate_raises_and_applies_no_points(self) -> None:
        apply_relationship_bump(
            source=self.source, target=self.target, interaction=self.interaction, valence=1
        )
        with self.assertRaises(AlreadyAcknowledgedError):
            apply_relationship_bump(
                source=self.source, target=self.target, interaction=self.interaction, valence=1
            )
        relationship = CharacterRelationship.objects.get(source=self.source, target=self.target)
        progress = RelationshipTrackProgress.objects.get(
            relationship=relationship, track=self.regard
        )
        self.assertEqual(progress.developed_points, BUMP_POINTS)
        self.assertEqual(RelationshipBump.objects.filter(relationship=relationship).count(), 1)

    def test_opposite_valence_on_same_interaction_still_deduped(self) -> None:
        apply_relationship_bump(
            source=self.source, target=self.target, interaction=self.interaction, valence=1
        )
        with self.assertRaises(AlreadyAcknowledgedError):
            apply_relationship_bump(
                source=self.source, target=self.target, interaction=self.interaction, valence=-1
            )

    def test_self_target_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            apply_relationship_bump(
                source=self.source, target=self.source, interaction=self.interaction, valence=1
            )

    def test_unseeded_tracks_raise(self) -> None:
        RelationshipTrack.objects.filter(system_key__isnull=False).delete()
        with self.assertRaises(SystemTracksNotSeededError):
            apply_relationship_bump(
                source=self.source, target=self.target, interaction=self.interaction, valence=1
            )


class RelationshipScaleSeedTests(TestCase):
    """The relationship_scale seed cluster is idempotent and re-applies edits."""

    def test_seed_idempotent_and_upserting(self) -> None:
        from world.relationships.models import RelationshipTier
        from world.scenes.models import ReactionEmoji
        from world.seeds.relationship_scale import seed_relationship_scale_content

        seed_relationship_scale_content()
        seed_relationship_scale_content()

        system_tracks = RelationshipTrack.objects.filter(system_key__isnull=False)
        self.assertEqual(system_tracks.count(), 2)
        regard = RelationshipTrack.objects.get(system_key=TrackSystemKey.REGARD)
        friction = RelationshipTrack.objects.get(system_key=TrackSystemKey.FRICTION)
        self.assertEqual(regard.sign, TrackSign.POSITIVE)
        self.assertEqual(friction.sign, TrackSign.NEGATIVE)

        tiers = RelationshipTier.objects.filter(track__in=[regard, friction])
        self.assertEqual(tiers.count(), 8)
        self.assertEqual(
            sorted(tiers.filter(track=regard).values_list("point_threshold", flat=True)),
            [25, 100, 500, 2000],
        )

        self.assertEqual(ReactionEmoji.objects.count(), 3)
        self.assertEqual(ReactionEmoji.objects.filter(valence=0).count(), 1)

        # Upsert re-applies an edited value on re-seed (loaddata can't — #946).
        regard.name = "Renamed"
        regard.save(update_fields=["name"])
        seed_relationship_scale_content()
        regard.refresh_from_db()
        self.assertEqual(regard.name, "Regard")
