"""Tests for relationship-building Actions."""

from actions.definitions.relationships import (
    CreateCapstoneAction,
    CreateDevelopmentAction,
    CreateFirstImpressionAction,
    RedistributePointsAction,
)
from actions.tests.utils import ActionTestCase
from world.relationships.factories import RelationshipTrackFactory
from world.relationships.models import (
    CharacterRelationship,
    RelationshipCapstone,
    RelationshipChange,
    RelationshipDevelopment,
    RelationshipTrackProgress,
)


class CreateFirstImpressionActionTests(ActionTestCase):
    def test_first_impression_creates_relationship(self):
        track = RelationshipTrackFactory()
        action = CreateFirstImpressionAction()

        result = action.run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=track,
            points=3,
            title="A striking introduction",
            writeup="They commanded the room.",
        )

        self.assertTrue(result.success)
        self.assertIn("first impression", result.message.lower())
        self.assertIn("relationship_id", result.data)
        relationship = CharacterRelationship.objects.get(pk=result.data["relationship_id"])
        self.assertEqual(relationship.source, self.actor_sheet)
        self.assertEqual(relationship.target, self.target_sheet)

    def test_first_impression_requires_track(self):
        action = CreateFirstImpressionAction()
        result = action.run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            points=3,
        )
        self.assertFalse(result.success)


class CreateDevelopmentActionTests(ActionTestCase):
    def test_development_solidifies_points(self):
        track = RelationshipTrackFactory()
        CreateFirstImpressionAction().run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=track,
            points=5,
            title="A striking introduction",
            writeup="They commanded the room.",
        )

        action = CreateDevelopmentAction()
        result = action.run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=track,
            points=3,
            title="Growing trust",
            writeup="We spoke for hours.",
        )

        self.assertTrue(result.success)
        development = RelationshipDevelopment.objects.get(pk=result.data["development_id"])
        self.assertEqual(development.points_earned, 3)
        progress = RelationshipTrackProgress.objects.get(
            relationship__source=self.actor_sheet,
            relationship__target=self.target_sheet,
            track=track,
        )
        self.assertEqual(progress.developed_points, 3)

    def test_development_fails_without_capacity(self):
        track = RelationshipTrackFactory()
        action = CreateDevelopmentAction()
        result = action.run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=track,
            points=3,
            title="Too soon",
            writeup="No foundation yet.",
        )
        self.assertFalse(result.success)


class CreateCapstoneActionTests(ActionTestCase):
    def test_capstone_adds_capacity_and_points(self):
        track = RelationshipTrackFactory()
        CreateFirstImpressionAction().run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=track,
            points=2,
            title="A striking introduction",
            writeup="They commanded the room.",
        )

        action = CreateCapstoneAction()
        result = action.run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=track,
            points=5,
            title="A defining moment",
            writeup="We stood back to back against the tide.",
        )

        self.assertTrue(result.success)
        capstone = RelationshipCapstone.objects.get(pk=result.data["capstone_id"])
        self.assertEqual(capstone.points, 5)
        progress = RelationshipTrackProgress.objects.get(
            relationship__source=self.actor_sheet,
            relationship__target=self.target_sheet,
            track=track,
        )
        self.assertEqual(progress.capacity, 7)
        self.assertEqual(progress.developed_points, 5)


class RedistributePointsActionTests(ActionTestCase):
    def test_redistribute_moves_points(self):
        source_track = RelationshipTrackFactory()
        target_track = RelationshipTrackFactory()
        CreateFirstImpressionAction().run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=source_track,
            points=5,
            title="A striking introduction",
            writeup="They commanded the room.",
        )
        CreateDevelopmentAction().run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=source_track,
            points=3,
            title="Growing trust",
            writeup="We spoke for hours.",
        )

        action = RedistributePointsAction()
        result = action.run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            source_track=source_track,
            target_track=target_track,
            points=2,
            title="Shifting focus",
            writeup="My regard finds a new shape.",
        )

        self.assertTrue(result.success)
        change = RelationshipChange.objects.get(pk=result.data["change_id"])
        self.assertEqual(change.points_moved, 2)
        self.assertEqual(change.source_track, source_track)
        self.assertEqual(change.target_track, target_track)

        source_progress = RelationshipTrackProgress.objects.get(
            relationship__source=self.actor_sheet,
            relationship__target=self.target_sheet,
            track=source_track,
        )
        target_progress = RelationshipTrackProgress.objects.get(
            relationship__source=self.actor_sheet,
            relationship__target=self.target_sheet,
            track=target_track,
        )
        self.assertEqual(source_progress.developed_points, 1)
        self.assertEqual(target_progress.developed_points, 2)

    def test_redistribute_requires_target_sheet(self):
        action = RedistributePointsAction()
        result = action.run(
            actor=self.actor,
            source_track=RelationshipTrackFactory(),
            target_track=RelationshipTrackFactory(),
            points=1,
        )
        self.assertFalse(result.success)
        self.assertIn("target", result.message.lower())

    def test_redistribute_requires_source_track(self):
        action = RedistributePointsAction()
        result = action.run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            target_track=RelationshipTrackFactory(),
            points=1,
        )
        self.assertFalse(result.success)
        self.assertIn("source track", result.message.lower())

    def test_redistribute_requires_target_track(self):
        action = RedistributePointsAction()
        result = action.run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            source_track=RelationshipTrackFactory(),
            points=1,
        )
        self.assertFalse(result.success)
        self.assertIn("target track", result.message.lower())

    def test_redistribute_fails_when_not_enough_points(self):
        source_track = RelationshipTrackFactory()
        target_track = RelationshipTrackFactory()
        CreateFirstImpressionAction().run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=source_track,
            points=5,
            title="A striking introduction",
            writeup="They commanded the room.",
        )
        CreateDevelopmentAction().run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=source_track,
            points=3,
            title="Growing trust",
            writeup="We spoke for hours.",
        )

        action = RedistributePointsAction()
        result = action.run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            source_track=source_track,
            target_track=target_track,
            points=5,
            title="Too much",
            writeup="My regard overreaches.",
        )
        self.assertFalse(result.success)

    def test_redistribute_fails_with_invalid_points(self):
        source_track = RelationshipTrackFactory()
        target_track = RelationshipTrackFactory()
        CreateFirstImpressionAction().run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=source_track,
            points=5,
            title="A striking introduction",
            writeup="They commanded the room.",
        )
        CreateDevelopmentAction().run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=source_track,
            points=3,
            title="Growing trust",
            writeup="We spoke for hours.",
        )

        action = RedistributePointsAction()
        result = action.run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            source_track=source_track,
            target_track=target_track,
            points="not-a-number",
            title="Shifting focus",
            writeup="My regard finds a new shape.",
        )
        self.assertFalse(result.success)
        self.assertIn("invalid", result.message.lower())
