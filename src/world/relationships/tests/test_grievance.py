"""Secret-victim grievances (#1429).

When a wronged character learns who harmed them, they choose a preset swing (or a custom value)
and ``register_grievance`` applies it as a one-sided relationship capstone toward the perpetrator.
The relationship stays ``is_pending`` (the victim's feelings are recorded without the
perpetrator's consent), and grievances must land on a negative-sign track.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import TrackSign
from world.relationships.factories import GrievanceOptionFactory, RelationshipTrackFactory
from world.relationships.models import CharacterRelationship, RelationshipTrackProgress
from world.relationships.services import register_grievance


class RegisterGrievanceTests(TestCase):
    def setUp(self) -> None:
        self.victim = CharacterSheetFactory()
        self.perpetrator = CharacterSheetFactory()
        self.negative_track = RelationshipTrackFactory(name="Enemies", sign=TrackSign.NEGATIVE)

    def _progress(self):
        relationship = CharacterRelationship.objects.get(
            source=self.victim, target=self.perpetrator
        )
        return relationship, RelationshipTrackProgress.objects.get(
            relationship=relationship, track=self.negative_track
        )

    def test_preset_grievance_applies_a_capstone_to_the_negative_track(self) -> None:
        option = GrievanceOptionFactory(
            label="Unforgivable Betrayal", track=self.negative_track, points=2000
        )

        capstone = register_grievance(source=self.victim, target=self.perpetrator, option=option)

        assert capstone.points == 2000
        assert capstone.title == "Unforgivable Betrayal"
        relationship, progress = self._progress()
        assert progress.developed_points == 2000
        assert progress.capacity == 2000
        # One-sided: the victim's regard is recorded without the perpetrator's consent.
        assert relationship.is_pending is True

    def test_custom_grievance_uses_provided_points_and_track(self) -> None:
        capstone = register_grievance(
            source=self.victim,
            target=self.perpetrator,
            custom_points=123,
            custom_track=self.negative_track,
        )

        assert capstone.points == 123
        _, progress = self._progress()
        assert progress.developed_points == 123

    def test_requires_an_option_or_a_custom_pair(self) -> None:
        with self.assertRaises(ValidationError):
            register_grievance(source=self.victim, target=self.perpetrator)

    def test_rejects_a_positive_sign_track(self) -> None:
        positive = RelationshipTrackFactory(name="Friendship", sign=TrackSign.POSITIVE)
        with self.assertRaises(ValidationError):
            register_grievance(
                source=self.victim,
                target=self.perpetrator,
                custom_points=100,
                custom_track=positive,
            )

    def test_grievance_option_clean_rejects_a_positive_track(self) -> None:
        positive = RelationshipTrackFactory(name="Admiration", sign=TrackSign.POSITIVE)
        option = GrievanceOptionFactory.build(label="Bad", track=positive, points=100)
        with self.assertRaises(ValidationError):
            option.full_clean()
