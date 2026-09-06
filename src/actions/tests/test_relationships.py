"""Tests for relationship-building Actions."""

from unittest.mock import PropertyMock, patch

from evennia.objects.models import ObjectDB

from actions.definitions.relationships import (
    CreateCapstoneAction,
    CreateDevelopmentAction,
    CreateFirstImpressionAction,
    RedistributePointsAction,
)
from actions.tests.utils import ActionTestCase
from world.character_sheets.models import CharacterSheet
from world.companions.factories import CompanionFactory
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


class TargetNameFallbackTests(ActionTestCase):
    """Ensure _target_name() falls back to a neutral message gracefully."""

    def _setup_relationship(self, track):
        """Create a relationship with a valid target character."""
        CreateFirstImpressionAction().run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=track,
            points=5,
            title="A striking introduction",
            writeup="They commanded the room.",
        )

    def _patch_character_missing(self):
        """Patch CharacterSheet.character to None without mutating the PK."""
        return patch.object(
            CharacterSheet,
            "character",
            new_callable=PropertyMock,
            return_value=None,
        )

    def test_first_impression_uses_neutral_message_when_target_character_missing(self):
        track = RelationshipTrackFactory()

        with self._patch_character_missing():
            result = CreateFirstImpressionAction().run(
                actor=self.actor,
                target_sheet=self.target_sheet,
                track=track,
                points=3,
                title="A striking introduction",
                writeup="They commanded the room.",
            )

        self.assertTrue(result.success)
        self.assertEqual(result.message, "You record a first impression.")

    def test_development_uses_neutral_message_when_target_character_missing(self):
        source_track = RelationshipTrackFactory()
        self._setup_relationship(source_track)

        with self._patch_character_missing():
            result = CreateDevelopmentAction().run(
                actor=self.actor,
                target_sheet=self.target_sheet,
                track=source_track,
                points=2,
                title="Growing trust",
                writeup="We spoke for hours.",
            )

        self.assertTrue(result.success)
        self.assertEqual(
            result.message,
            f"You develop your regard (2 points on {source_track.name}).",
        )

    def test_capstone_uses_neutral_message_when_target_character_missing(self):
        track = RelationshipTrackFactory()
        self._setup_relationship(track)

        with self._patch_character_missing():
            result = CreateCapstoneAction().run(
                actor=self.actor,
                target_sheet=self.target_sheet,
                track=track,
                points=3,
                title="A defining moment",
                writeup="We stood back to back against the tide.",
            )

        self.assertTrue(result.success)
        self.assertEqual(
            result.message,
            f"You mark a capstone in your regard ({track.name}).",
        )

    def test_redistribute_uses_neutral_message_when_target_character_missing(self):
        source_track = RelationshipTrackFactory()
        target_track = RelationshipTrackFactory()
        self._setup_relationship(source_track)
        CreateDevelopmentAction().run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            track=source_track,
            points=3,
            title="Growing trust",
            writeup="We spoke for hours.",
        )

        with self._patch_character_missing():
            result = RedistributePointsAction().run(
                actor=self.actor,
                target_sheet=self.target_sheet,
                source_track=source_track,
                target_track=target_track,
                points=2,
                title="Shifting focus",
                writeup="My regard finds a new shape.",
            )

        self.assertTrue(result.success)
        self.assertEqual(
            result.message,
            (f"You shift 2 points from {source_track.name} to {target_track.name}."),
        )

    def test_target_name_returns_none_when_character_missing(self):
        """_target_name catches AttributeError and returns None."""

        class MissingCharacterSheet:
            character = None

        action = CreateFirstImpressionAction()
        self.assertIsNone(action._target_name(MissingCharacterSheet()))

    def test_target_name_returns_none_when_character_raises_does_not_exist(self):
        """_target_name catches ObjectDoesNotExist and returns None."""
        deleted_message = "Character deleted"

        class MissingCharacterSheet:
            @property
            def character(self):
                raise ObjectDB.DoesNotExist(deleted_message)

        action = CreateFirstImpressionAction()
        self.assertIsNone(action._target_name(MissingCharacterSheet()))


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


class SelfTargetGuardTests(ActionTestCase):
    """No verb may record a relationship with the actor's own character (#1485)."""

    def test_first_impression_rejects_self_target(self):
        track = RelationshipTrackFactory()
        result = CreateFirstImpressionAction().run(
            actor=self.actor,
            target_sheet=self.actor_sheet,
            track=track,
            points=3,
            title="Navel-gazing",
            writeup="I find myself fascinating.",
        )
        self.assertFalse(result.success)
        self.assertIn("yourself", result.message.lower())
        self.assertFalse(
            CharacterRelationship.objects.filter(
                source=self.actor_sheet, target=self.actor_sheet
            ).exists()
        )

    def test_development_rejects_self_target(self):
        track = RelationshipTrackFactory()
        result = CreateDevelopmentAction().run(
            actor=self.actor,
            target_sheet=self.actor_sheet,
            track=track,
            points=2,
            title="Growing self-regard",
            writeup="I grow on me.",
        )
        self.assertFalse(result.success)
        self.assertIn("yourself", result.message.lower())

    def test_capstone_rejects_self_target(self):
        track = RelationshipTrackFactory()
        result = CreateCapstoneAction().run(
            actor=self.actor,
            target_sheet=self.actor_sheet,
            track=track,
            points=10,
            title="Self oath",
            writeup="I swore to myself.",
        )
        self.assertFalse(result.success)
        self.assertIn("yourself", result.message.lower())

    def test_redistribute_rejects_self_target(self):
        source_track = RelationshipTrackFactory()
        target_track = RelationshipTrackFactory()
        result = RedistributePointsAction().run(
            actor=self.actor,
            target_sheet=self.actor_sheet,
            source_track=source_track,
            target_track=target_track,
            points=3,
            title="Self shift",
            writeup="Reconfiguring my self-regard.",
        )
        self.assertFalse(result.success)
        self.assertIn("yourself", result.message.lower())


class CompanionTargetActionTests(ActionTestCase):
    def setUp(self):
        super().setUp()
        self.companion = CompanionFactory(owner=self.actor_sheet, name="Ash")
        self.track = RelationshipTrackFactory()

    def _impress(self, **overrides):
        kwargs = {
            "actor": self.actor,
            "target_companion": self.companion,
            "track": self.track,
            "points": 3,
            "title": "Ash at the gate",
            "writeup": "It did not flinch.",
        }
        kwargs.update(overrides)
        return CreateFirstImpressionAction().run(**kwargs)

    def test_first_impression_toward_own_companion(self):
        result = self._impress()
        self.assertTrue(result.success, result.message)
        self.assertIn("Ash", result.message)
        relationship = CharacterRelationship.objects.get(pk=result.data["relationship_id"])
        self.assertEqual(relationship.target_companion, self.companion)
        self.assertFalse(relationship.is_pending)

    def test_first_impression_toward_someone_elses_companion_is_refused(self):
        stranger_companion = CompanionFactory(name="Not Yours")
        result = self._impress(target_companion=stranger_companion)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "That companion is not bonded to you.")

    def test_development_and_capstone_toward_companion(self):
        self._impress()
        dev = CreateDevelopmentAction().run(
            actor=self.actor,
            target_companion=self.companion,
            track=self.track,
            points=2,
            title="Held the line",
            writeup="Stood between me and the blade.",
        )
        self.assertTrue(dev.success, dev.message)
        cap = CreateCapstoneAction().run(
            actor=self.actor,
            target_companion=self.companion,
            track=self.track,
            points=4,
            title="Bled for me",
            writeup="It nearly died.",
        )
        self.assertTrue(cap.success, cap.message)
        relationship = CharacterRelationship.objects.get(
            source=self.actor_sheet, target_companion=self.companion
        )
        progress = RelationshipTrackProgress.objects.get(
            relationship=relationship, track=self.track
        )
        self.assertEqual(progress.developed_points, 6)

    def test_redistribute_toward_companion(self):
        other_track = RelationshipTrackFactory()
        self._impress()
        CreateCapstoneAction().run(
            actor=self.actor,
            target_companion=self.companion,
            track=self.track,
            points=4,
            title="Bled for me",
            writeup="It nearly died.",
        )
        result = RedistributePointsAction().run(
            actor=self.actor,
            target_companion=self.companion,
            source_track=self.track,
            target_track=other_track,
            points=2,
            title="Shifting",
            writeup="Less awe, more trust.",
        )
        self.assertTrue(result.success, result.message)
        self.assertIn("Ash", result.message)

    def test_no_target_at_all_is_refused(self):
        result = CreateFirstImpressionAction().run(
            actor=self.actor, track=self.track, points=3, title="x", writeup="y"
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message, "No target selected.")
