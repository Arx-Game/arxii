"""Tests for relationships service functions."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.achievements.factories import StatDefinitionFactory
from world.achievements.models import StatTracker
from world.character_sheets.factories import CharacterSheetFactory
from world.progression.models import ExperiencePointsData
from world.relationships.constants import (
    MAX_DEVELOPMENTS_PER_WEEK,
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
    RelationshipCapstone,
    RelationshipDevelopment,
    RelationshipTrackProgress,
    RelationshipUpdate,
)
from world.relationships.services import (
    create_capstone,
    create_development,
    create_first_impression,
    redistribute_points,
)
from world.roster.factories import RosterTenureFactory


class CreateFirstImpressionTest(TestCase):
    """Tests for create_first_impression service function."""

    @classmethod
    def setUpTestData(cls):
        cls.source = CharacterSheetFactory()
        cls.target = CharacterSheetFactory()
        cls.track = RelationshipTrackFactory(name="Trust", sign=TrackSign.POSITIVE)
        # Required by create_first_impression when reciprocation triggers increment_stat
        cls.rel_stat = StatDefinitionFactory(
            key="relationships.total_established", name="Relationships Established"
        )

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

    def test_creates_track_progress_with_capacity(self):
        """create_first_impression creates TrackProgress with capacity set."""
        rel = self._call()
        progress = RelationshipTrackProgress.objects.get(relationship=rel, track=self.track)
        self.assertEqual(progress.capacity, 5)
        self.assertEqual(progress.developed_points, 0)

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

        source_stat = StatTracker.objects.get(character_sheet=self.source, stat=self.rel_stat)
        target_stat = StatTracker.objects.get(character_sheet=self.target, stat=self.rel_stat)
        self.assertEqual(source_stat.value, 1)
        self.assertEqual(target_stat.value, 1)

    def test_duplicate_first_impression_raises(self):
        """Second first impression for same source->target raises ValidationError."""
        self._call()
        with self.assertRaises(ValidationError):
            self._call()

    def test_awards_xp_to_author_and_target(self):
        """First impression awards 3 XP to author and 5 XP to target."""
        source_sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        source_tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=source_sheet.character,
        )
        target_tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=target_sheet.character,
        )
        source_account = source_tenure.player_data.account
        target_account = target_tenure.player_data.account

        self._call(source=source_sheet, target=target_sheet)

        source_xp = ExperiencePointsData.objects.get(account=source_account)
        target_xp = ExperiencePointsData.objects.get(account=target_account)
        self.assertEqual(source_xp.total_earned, 3)
        self.assertEqual(target_xp.total_earned, 5)


class RedistributePointsTest(TestCase):
    """Tests for redistribute_points service function."""

    @classmethod
    def setUpTestData(cls):
        cls.source_track = RelationshipTrackFactory(name="RedistTrust", sign=TrackSign.POSITIVE)
        cls.target_track = RelationshipTrackFactory(name="RedistFear", sign=TrackSign.NEGATIVE)
        cls.sheet = CharacterSheetFactory()

    def _make_relationship_with_progress(self, developed_points=20):
        rel = CharacterRelationshipFactory(source=self.sheet)
        RelationshipTrackProgressFactory(
            relationship=rel,
            track=self.source_track,
            capacity=developed_points,
            developed_points=developed_points,
        )
        return rel

    def test_moves_points_between_tracks(self):
        """redistribute_points decreases source track and increases target track."""
        rel = self._make_relationship_with_progress(developed_points=20)

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
        self.assertEqual(source_progress.developed_points, 12)
        self.assertEqual(target_progress.developed_points, 8)

    def test_developed_value_unchanged(self):
        """Total developed value before and after redistribution is the same."""
        rel = self._make_relationship_with_progress(developed_points=20)
        value_before = rel.developed_absolute_value

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

        rel = CharacterRelationship.objects.get(pk=rel.pk)
        self.assertEqual(rel.developed_absolute_value, value_before)

    def test_cannot_move_more_than_available(self):
        """Raises ValidationError when trying to move more points than available."""
        rel = self._make_relationship_with_progress(developed_points=5)

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

    def test_no_source_progress_raises(self):
        """Raises ValidationError when source track has no progress at all."""
        rel = CharacterRelationshipFactory(source=self.sheet)

        with self.assertRaises(ValidationError):
            redistribute_points(
                relationship=rel,
                author=self.sheet,
                title="No Source",
                writeup="Nothing to move.",
                source_track=self.source_track,
                target_track=self.target_track,
                points=5,
                visibility=UpdateVisibility.SHARED,
            )


class CreateDevelopmentTest(TestCase):
    """Tests for create_development service function."""

    @classmethod
    def setUpTestData(cls):
        cls.track = RelationshipTrackFactory(name="DevTrack", sign=TrackSign.POSITIVE)
        cls.sheet = CharacterSheetFactory()

    def test_adds_permanent_points(self):
        """create_development adds to developed_points."""
        rel = CharacterRelationshipFactory(source=self.sheet)
        RelationshipTrackProgressFactory(
            relationship=rel, track=self.track, capacity=100, developed_points=0
        )

        dev = create_development(
            relationship=rel,
            author=self.sheet,
            title="Reflection",
            writeup="Thought about our bond.",
            track=self.track,
            points=15,
            xp_awarded=5,
            visibility=UpdateVisibility.SHARED,
        )

        progress = RelationshipTrackProgress.objects.get(relationship=rel, track=self.track)
        self.assertEqual(progress.developed_points, 15)
        self.assertEqual(dev.points_earned, 15)
        self.assertEqual(dev.xp_awarded, 5)

    def test_capped_at_capacity(self):
        """Development points are capped at remaining capacity."""
        rel = CharacterRelationshipFactory(source=self.sheet)
        RelationshipTrackProgressFactory(
            relationship=rel, track=self.track, capacity=20, developed_points=15
        )

        dev = create_development(
            relationship=rel,
            author=self.sheet,
            title="Push",
            writeup="Tried to develop more.",
            track=self.track,
            points=10,
            visibility=UpdateVisibility.SHARED,
        )

        progress = RelationshipTrackProgress.objects.get(relationship=rel, track=self.track)
        self.assertEqual(progress.developed_points, 20)
        self.assertEqual(dev.points_earned, 5)  # Only 5 capacity remaining

    def test_fails_when_no_capacity(self):
        """Raises ValidationError when track is at full capacity."""
        rel = CharacterRelationshipFactory(source=self.sheet)
        RelationshipTrackProgressFactory(
            relationship=rel, track=self.track, capacity=20, developed_points=20
        )

        with self.assertRaises(ValidationError):
            create_development(
                relationship=rel,
                author=self.sheet,
                title="Over",
                writeup="No room.",
                track=self.track,
                points=5,
                visibility=UpdateVisibility.SHARED,
            )

    def test_creates_development_record(self):
        """create_development creates a RelationshipDevelopment record."""
        rel = CharacterRelationshipFactory(source=self.sheet)
        RelationshipTrackProgressFactory(
            relationship=rel, track=self.track, capacity=100, developed_points=0
        )

        create_development(
            relationship=rel,
            author=self.sheet,
            title="Record",
            writeup="Testing record creation.",
            track=self.track,
            points=10,
            visibility=UpdateVisibility.SHARED,
        )

        self.assertEqual(RelationshipDevelopment.objects.filter(relationship=rel).count(), 1)

    def test_weekly_limit_enforced(self):
        """Cannot exceed MAX_DEVELOPMENTS_PER_WEEK developments."""
        rel = CharacterRelationshipFactory(source=self.sheet)
        RelationshipTrackProgressFactory(
            relationship=rel, track=self.track, capacity=1000, developed_points=0
        )

        for i in range(MAX_DEVELOPMENTS_PER_WEEK):
            create_development(
                relationship=rel,
                author=self.sheet,
                title=f"Dev {i}",
                writeup="Developing.",
                track=self.track,
                points=1,
                visibility=UpdateVisibility.SHARED,
            )
            rel.refresh_from_db()

        with self.assertRaises(ValidationError):
            create_development(
                relationship=rel,
                author=self.sheet,
                title="Over Limit",
                writeup="Too many.",
                track=self.track,
                points=1,
                visibility=UpdateVisibility.SHARED,
            )

    def test_weekly_limit_resets_on_new_game_week(self):
        """Weekly counter resets when the game week changes."""
        from world.game_clock.week_services import advance_game_week, get_current_game_week

        old_week = get_current_game_week()
        rel = CharacterRelationshipFactory(source=self.sheet, game_week=old_week)
        RelationshipTrackProgressFactory(
            relationship=rel, track=self.track, capacity=1000, developed_points=0
        )

        # Simulate having hit the limit last week
        rel.developments_this_week = MAX_DEVELOPMENTS_PER_WEEK
        rel.save(update_fields=["developments_this_week"])

        # Advance to a new game week
        advance_game_week()

        # Should succeed because the week has rolled over
        dev = create_development(
            relationship=rel,
            author=self.sheet,
            title="Fresh Week",
            writeup="New week.",
            track=self.track,
            points=1,
            visibility=UpdateVisibility.SHARED,
        )
        self.assertEqual(dev.points_earned, 1)
        rel.refresh_from_db()
        self.assertEqual(rel.developments_this_week, 1)

    def test_increments_developments_this_week(self):
        """Each development increments developments_this_week."""
        rel = CharacterRelationshipFactory(source=self.sheet)
        RelationshipTrackProgressFactory(
            relationship=rel, track=self.track, capacity=100, developed_points=0
        )

        create_development(
            relationship=rel,
            author=self.sheet,
            title="First",
            writeup="First.",
            track=self.track,
            points=1,
            visibility=UpdateVisibility.SHARED,
        )

        rel.refresh_from_db()
        self.assertEqual(rel.developments_this_week, 1)


class CreateCapstoneTest(TestCase):
    """Tests for create_capstone service function."""

    @classmethod
    def setUpTestData(cls):
        cls.track = RelationshipTrackFactory(name="CapTrack", sign=TrackSign.POSITIVE)
        cls.sheet = CharacterSheetFactory()

    def test_adds_capacity_and_developed(self):
        """create_capstone increases both capacity and developed_points."""
        rel = CharacterRelationshipFactory(source=self.sheet)
        RelationshipTrackProgressFactory(
            relationship=rel, track=self.track, capacity=30, developed_points=30
        )

        create_capstone(
            relationship=rel,
            author=self.sheet,
            title="Saved My Life",
            writeup="They dove in front of the blade.",
            track=self.track,
            points=1000,
            visibility=UpdateVisibility.SHARED,
        )

        progress = RelationshipTrackProgress.objects.get(relationship=rel, track=self.track)
        self.assertEqual(progress.capacity, 1030)
        self.assertEqual(progress.developed_points, 1030)

    def test_creates_capstone_record(self):
        """create_capstone creates a RelationshipCapstone record."""
        rel = CharacterRelationshipFactory(source=self.sheet)
        RelationshipTrackProgressFactory(
            relationship=rel, track=self.track, capacity=0, developed_points=0
        )

        cap = create_capstone(
            relationship=rel,
            author=self.sheet,
            title="Monumental",
            writeup="A defining moment.",
            track=self.track,
            points=500,
            visibility=UpdateVisibility.SHARED,
        )

        self.assertEqual(RelationshipCapstone.objects.filter(relationship=rel).count(), 1)
        self.assertEqual(cap.points, 500)

    def test_capstone_on_empty_track(self):
        """Capstone works even on a track with no prior progress."""
        rel = CharacterRelationshipFactory(source=self.sheet)

        create_capstone(
            relationship=rel,
            author=self.sheet,
            title="From Nothing",
            writeup="Out of nowhere.",
            track=self.track,
            points=100,
            visibility=UpdateVisibility.SHARED,
        )

        progress = RelationshipTrackProgress.objects.get(relationship=rel, track=self.track)
        self.assertEqual(progress.capacity, 100)
        self.assertEqual(progress.developed_points, 100)

    def test_user_example_scenario(self):
        """Test the example from the design: dislike + hatred update + capstone."""
        enemies_track = RelationshipTrackFactory(name="Enemies", sign=TrackSign.NEGATIVE)
        rel = CharacterRelationshipFactory(source=self.sheet)

        # Start with 30 developed dislike
        RelationshipTrackProgressFactory(
            relationship=rel, track=enemies_track, capacity=30, developed_points=30
        )

        # 50-point relationship update (hatred) — adds 50 capacity, 50 temporary

        RelationshipUpdate.objects.create(
            relationship=rel,
            author=self.sheet,
            title="Hatred",
            writeup="Pure hatred.",
            track=enemies_track,
            points_earned=50,
        )
        progress = RelationshipTrackProgress.objects.get(relationship=rel, track=enemies_track)
        progress.capacity += 50  # Update adds to capacity
        progress.save(update_fields=["capacity"])

        progress.refresh_from_db()
        self.assertEqual(progress.capacity, 80)
        self.assertEqual(progress.developed_points, 30)

        # Capstone: saved my life (+1000 to both)
        create_capstone(
            relationship=rel,
            author=self.sheet,
            title="Saved My Life",
            writeup="They saved me.",
            track=enemies_track,
            points=1000,
            visibility=UpdateVisibility.SHARED,
        )

        progress.refresh_from_db()
        self.assertEqual(progress.capacity, 1080)
        self.assertEqual(progress.developed_points, 1030)
