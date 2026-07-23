"""Tests for RelationshipRequirement — character-intrinsic track/tier gate (#2116).

Schema rework: dropped the freeform `relationship_target`/`minimum_level` stub
(previously hardcoded `return False`) for `required_track_kind` (nullable — null
= any track) + `minimum_tier` + `minimum_count`, implemented as a
RelationshipTrackProgress tier-count query against the character's OWN tracks.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory
from world.progression.models import ClassLevelUnlock, RelationshipRequirement
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTierFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)


def _make_track_with_tiers(name: str) -> RelationshipTrackFactory:
    """Build a track with tiers 1 (threshold 10), 2 (threshold 20), 3 (threshold 30)."""
    track = RelationshipTrackFactory(name=name)
    RelationshipTierFactory(track=track, tier_number=1, point_threshold=10, name="T1")
    RelationshipTierFactory(track=track, tier_number=2, point_threshold=20, name="T2")
    RelationshipTierFactory(track=track, tier_number=3, point_threshold=30, name="T3")
    return track


class RelationshipRequirementBoundaryTierTests(TestCase):
    """met/unmet against seeded RelationshipTrackProgress at/below/above the tier threshold."""

    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.track = _make_track_with_tiers("Trust")

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)
        self.other_sheet = CharacterSheetFactory()

    def _progress_at(self, developed_points: int):
        relationship = CharacterRelationshipFactory(
            source=self.sheet, target=self.other_sheet, is_active=True
        )
        return RelationshipTrackProgressFactory(
            relationship=relationship, track=self.track, developed_points=developed_points
        )

    def test_below_tier_threshold_is_unmet(self) -> None:
        # tier 2 threshold is 20; 19 points → still tier 1.
        self._progress_at(19)
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_track_kind=self.track,
            minimum_tier=2,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is False

    def test_at_tier_threshold_boundary_is_met(self) -> None:
        # Exactly at tier 2's threshold (20 points).
        self._progress_at(20)
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_track_kind=self.track,
            minimum_tier=2,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is True

    def test_above_tier_threshold_is_met(self) -> None:
        self._progress_at(35)
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_track_kind=self.track,
            minimum_tier=2,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is True

    def test_no_relationship_at_all_is_unmet(self) -> None:
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_track_kind=self.track,
            minimum_tier=1,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is False


class RelationshipRequirementTrackKindTests(TestCase):
    """required_track_kind narrows the count; null means any track qualifies."""

    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.trust_track = _make_track_with_tiers("Trust2")
        cls.respect_track = _make_track_with_tiers("Respect2")

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)
        self.other_sheet = CharacterSheetFactory()
        self.relationship = CharacterRelationshipFactory(
            source=self.sheet, target=self.other_sheet, is_active=True
        )

    def test_specific_track_kind_ignores_other_tracks(self) -> None:
        RelationshipTrackProgressFactory(
            relationship=self.relationship, track=self.respect_track, developed_points=30
        )
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_track_kind=self.trust_track,
            minimum_tier=1,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is False

    def test_null_track_kind_matches_any_track(self) -> None:
        RelationshipTrackProgressFactory(
            relationship=self.relationship, track=self.respect_track, developed_points=30
        )
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_track_kind=None,
            minimum_tier=1,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is True


class RelationshipRequirementMinimumCountTests(TestCase):
    """minimum_count requires that many distinct qualifying tracks."""

    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.track_a = _make_track_with_tiers("TrackA")
        cls.track_b = _make_track_with_tiers("TrackB")

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)
        self.other_sheet = CharacterSheetFactory()
        self.relationship = CharacterRelationshipFactory(
            source=self.sheet, target=self.other_sheet, is_active=True
        )

    def test_one_qualifying_track_insufficient_for_count_two(self) -> None:
        RelationshipTrackProgressFactory(
            relationship=self.relationship, track=self.track_a, developed_points=30
        )
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_track_kind=None,
            minimum_tier=1,
            minimum_count=2,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is False

    def test_two_qualifying_tracks_meets_count_two(self) -> None:
        RelationshipTrackProgressFactory(
            relationship=self.relationship, track=self.track_a, developed_points=30
        )
        RelationshipTrackProgressFactory(
            relationship=self.relationship, track=self.track_b, developed_points=30
        )
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_track_kind=None,
            minimum_tier=1,
            minimum_count=2,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is True


class RelationshipRequirementNoLeakTests(TestCase):
    """Unmet text renders only the authored gate + the character's own progress."""

    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.track = _make_track_with_tiers("Secretive")

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)
        self.other_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="OtherParty"))

    def test_unmet_message_never_names_other_character(self) -> None:
        relationship = CharacterRelationshipFactory(
            source=self.sheet, target=self.other_sheet, is_active=True
        )
        RelationshipTrackProgressFactory(
            relationship=relationship, track=self.track, developed_points=5
        )
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_track_kind=self.track,
            minimum_tier=3,
            minimum_count=1,
        )
        met, message = req.is_met_by_character(self.character)
        assert met is False
        assert "OtherParty" not in message

    def test_str_renders_authored_gate(self) -> None:
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_track_kind=self.track,
            minimum_tier=2,
            minimum_count=3,
        )
        text = str(req)
        assert "Secretive" in text
        assert "2" in text
        assert "3" in text
