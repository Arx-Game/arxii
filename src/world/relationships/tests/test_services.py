"""Tests for relationships service functions."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.achievements.models import StatTracker
from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import (
    FirstImpressionColoring,
    TrackSign,
    UpdateVisibility,
)
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.relationships.models import (
    CharacterRelationship,
    RelationshipTrackProgress,
    RelationshipUpdate,
)
from world.relationships.services import create_first_impression, redistribute_points


class CreateFirstImpressionTest(TestCase):
    """Tests for create_first_impression service function."""

    @classmethod
    def setUpTestData(cls):
        cls.source = CharacterSheetFactory()
        cls.target = CharacterSheetFactory()
        cls.track = RelationshipTrackFactory(name="Trust", sign=TrackSign.POSITIVE)

    def _call(self, **overrides):
        defaults = {
            "source": self.source,
            "target": self.target,
            "title": "First Meeting",
            "writeup": "We met at the tavern.",
            "track": self.track,
            "points": 5,
            "coloring": FirstImpressionColoring.POSITIVE,
            "visibility": UpdateVisibility.SHARED,
        }
        defaults.update(overrides)
        return create_first_impression(**defaults)

    def test_creates_pending_relationship(self):
        """create_first_impression creates a relationship with is_pending=True."""
        rel = self._call()
        self.assertTrue(rel.is_pending)
        self.assertEqual(rel.source, self.source)
        self.assertEqual(rel.target, self.target)

    def test_creates_update_record(self):
        """create_first_impression creates a RelationshipUpdate with is_first_impression=True."""
        rel = self._call()
        update = RelationshipUpdate.objects.get(relationship=rel)
        self.assertTrue(update.is_first_impression)
        self.assertEqual(update.track, self.track)
        self.assertEqual(update.points_earned, 5)
        self.assertEqual(update.author, self.source)
        self.assertEqual(update.coloring, FirstImpressionColoring.POSITIVE)

    def test_creates_track_progress(self):
        """create_first_impression creates RelationshipTrackProgress with correct points."""
        rel = self._call()
        progress = RelationshipTrackProgress.objects.get(relationship=rel, track=self.track)
        self.assertEqual(progress.points, 5)

    def test_reciprocal_impression_activates_both(self):
        """After both players do first impressions, both rels have is_pending=False."""
        rel_ab = self._call(source=self.source, target=self.target)
        self.assertTrue(rel_ab.is_pending)

        # Target does a first impression back
        track2 = RelationshipTrackFactory(name="Respect", sign=TrackSign.POSITIVE)
        rel_ba = self._call(source=self.target, target=self.source, track=track2)

        self.assertFalse(rel_ba.is_pending)
        rel_ab.refresh_from_db()
        self.assertFalse(rel_ab.is_pending)

    def test_increments_achievement_stat(self):
        """After reciprocation, both characters get 'relationships.total_established' stat."""
        self._call(source=self.source, target=self.target)

        track2 = RelationshipTrackFactory(name="Admiration", sign=TrackSign.POSITIVE)
        self._call(source=self.target, target=self.source, track=track2)

        source_stat = StatTracker.objects.get(
            character_sheet=self.source, stat_key="relationships.total_established"
        )
        target_stat = StatTracker.objects.get(
            character_sheet=self.target, stat_key="relationships.total_established"
        )
        self.assertEqual(source_stat.value, 1)
        self.assertEqual(target_stat.value, 1)


class RedistributePointsTest(TestCase):
    """Tests for redistribute_points service function."""

    @classmethod
    def setUpTestData(cls):
        cls.source_track = RelationshipTrackFactory(name="RedistTrust", sign=TrackSign.POSITIVE)
        cls.target_track = RelationshipTrackFactory(name="RedistFear", sign=TrackSign.NEGATIVE)
        cls.sheet = CharacterSheetFactory()

    def _make_relationship_with_progress(self, points=20):
        rel = CharacterRelationshipFactory(source=self.sheet)
        RelationshipTrackProgressFactory(relationship=rel, track=self.source_track, points=points)
        return rel

    def test_moves_points_between_tracks(self):
        """redistribute_points decreases source track and increases target track."""
        rel = self._make_relationship_with_progress(points=20)

        redistribute_points(
            relationship=rel,
            author=self.sheet,
            title="Shift",
            writeup="Trust eroded into fear.",
            source_track=self.source_track,
            target_track=self.target_track,
            points=8,
            visibility=UpdateVisibility.SHARED,
        )

        source_progress = RelationshipTrackProgress.objects.get(
            relationship=rel, track=self.source_track
        )
        target_progress = RelationshipTrackProgress.objects.get(
            relationship=rel, track=self.target_track
        )
        self.assertEqual(source_progress.points, 12)
        self.assertEqual(target_progress.points, 8)

    def test_absolute_value_unchanged(self):
        """Total absolute value before and after redistribution is the same."""
        rel = self._make_relationship_with_progress(points=20)
        value_before = rel.absolute_value

        redistribute_points(
            relationship=rel,
            author=self.sheet,
            title="Shift",
            writeup="Shift happened.",
            source_track=self.source_track,
            target_track=self.target_track,
            points=8,
            visibility=UpdateVisibility.SHARED,
        )

        # Refresh to pick up new track_progress entries
        rel = CharacterRelationship.objects.get(pk=rel.pk)
        self.assertEqual(rel.absolute_value, value_before)

    def test_cannot_move_more_than_available(self):
        """Raises ValidationError when trying to move more points than available."""
        rel = self._make_relationship_with_progress(points=5)

        with self.assertRaises(ValidationError):
            redistribute_points(
                relationship=rel,
                author=self.sheet,
                title="Too Much",
                writeup="Trying to move too many.",
                source_track=self.source_track,
                target_track=self.target_track,
                points=10,
                visibility=UpdateVisibility.SHARED,
            )
