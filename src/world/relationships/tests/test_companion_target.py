"""Companion-targeted relationships (#3575): model constraints and display."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.companions.factories import CompanionFactory
from world.progression.models import ExperiencePointsData
from world.relationships.constants import FirstImpressionColoring, TrackSign, UpdateVisibility
from world.relationships.exceptions import NotWriteupSubjectError
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
)
from world.relationships.models import CharacterRelationship
from world.relationships.services import (
    companion_target_error,
    create_first_impression,
    give_writeup_kudos,
)
from world.roster.factories import RosterTenureFactory, grant_test_tenure


class CompanionTargetModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = CharacterSheetFactory()
        cls.companion = CompanionFactory(owner=cls.owner, name="Ash")

    def test_companion_target_row_saves_and_names_the_companion(self) -> None:
        rel = CharacterRelationshipFactory(
            source=self.owner, target=None, target_companion=self.companion
        )
        self.assertIsNone(rel.target)
        self.assertEqual(rel.target_companion, self.companion)
        self.assertEqual(rel.target_name, "Ash")
        self.assertIn("Ash", str(rel))

    def test_sheet_target_name_is_the_character_key(self) -> None:
        rel = CharacterRelationshipFactory(source=self.owner)
        self.assertEqual(rel.target_name, rel.target.character.db_key)

    def test_clean_rejects_both_targets(self) -> None:
        other = CharacterSheetFactory()
        rel = CharacterRelationship(
            source=self.owner, target=other, target_companion=self.companion
        )
        with self.assertRaises(ValidationError):
            rel.clean()

    def test_clean_rejects_no_target(self) -> None:
        rel = CharacterRelationship(source=self.owner)
        with self.assertRaises(ValidationError):
            rel.clean()

    def test_db_rejects_both_targets(self) -> None:
        other = CharacterSheetFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterRelationship.objects.create(
                source=self.owner, target=other, target_companion=self.companion
            )

    def test_db_rejects_no_target(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterRelationship.objects.create(source=self.owner)

    def test_one_row_per_companion_per_source(self) -> None:
        CharacterRelationshipFactory(
            source=self.owner, target=None, target_companion=self.companion
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterRelationship.objects.create(source=self.owner, target_companion=self.companion)

    def test_sheet_pair_uniqueness_survives(self) -> None:
        other = CharacterSheetFactory()
        CharacterRelationshipFactory(source=self.owner, target=other)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterRelationship.objects.create(source=self.owner, target=other)

    def test_two_companions_two_rows(self) -> None:
        second = CompanionFactory(owner=self.owner, name="Ember")
        CharacterRelationshipFactory(
            source=self.owner, target=None, target_companion=self.companion
        )
        CharacterRelationshipFactory(source=self.owner, target=None, target_companion=second)
        self.assertEqual(CharacterRelationship.objects.filter(source=self.owner).count(), 2)


class CompanionFirstImpressionServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = CharacterSheetFactory()
        cls.companion = CompanionFactory(owner=cls.owner, name="Ash")
        cls.track = RelationshipTrackFactory(sign=TrackSign.POSITIVE)

    def _impress(self, **overrides):
        kwargs = {
            "source": self.owner,
            "target_companion": self.companion,
            "title": "Ash at the gate",
            "writeup": "It did not flinch.",
            "track": self.track,
            "points": 5,
            "coloring": FirstImpressionColoring.POSITIVE,
            "visibility": UpdateVisibility.PRIVATE,
        }
        kwargs.update(overrides)
        return create_first_impression(**kwargs)

    def test_owner_row_is_active_from_creation(self) -> None:
        rel = self._impress()
        self.assertFalse(rel.is_pending)
        self.assertTrue(rel.is_active)
        self.assertEqual(rel.target_companion, self.companion)
        self.assertIsNone(rel.target)
        progress = rel.track_progress.get(track=self.track)
        self.assertEqual(progress.capacity, 5)

    def test_non_owner_is_refused(self) -> None:
        stranger = CharacterSheetFactory()
        self.assertEqual(
            companion_target_error(stranger, self.companion), "That companion is not bonded to you."
        )
        with self.assertRaises(ValidationError):
            self._impress(source=stranger)
        self.assertFalse(CharacterRelationship.objects.filter(source=stranger).exists())

    def test_released_companion_is_refused(self) -> None:
        from django.utils import timezone

        released = CompanionFactory(owner=self.owner, released_at=timezone.now())
        self.assertEqual(
            companion_target_error(self.owner, released), "That companion has been released."
        )
        with self.assertRaises(ValidationError):
            self._impress(target_companion=released)

    def test_exactly_one_target_required(self) -> None:
        other = CharacterSheetFactory()
        with self.assertRaises(ValidationError):
            self._impress(target=other)
        with self.assertRaises(ValidationError):
            self._impress(target_companion=None)

    def test_author_xp_but_no_target_xp(self) -> None:
        tenure = grant_test_tenure(self.owner)
        self._impress()
        xp = ExperiencePointsData.objects.get(account=tenure.player_data.account)
        self.assertGreater(xp.total_earned, 0)

    def test_companion_writeup_cannot_be_commended(self) -> None:
        rel = self._impress(visibility=UpdateVisibility.SHARED)
        writeup = rel.updates.get(is_first_impression=True)
        other_tenure = RosterTenureFactory()
        with self.assertRaises(NotWriteupSubjectError):
            give_writeup_kudos(giver_account=other_tenure.player_data.account, writeup=writeup)
