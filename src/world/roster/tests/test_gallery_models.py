"""The gallery's model rules (#4151): a look's crop, character art, and hiding it."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.roster.factories import (
    RosterEntryFactory,
    RosterTenureFactory,
    TenureMediaFactory,
)
from world.roster.models import HiddenCharacterArt, TenureMedia


class TenureMediaCropTests(TestCase):
    """A crop is all three numbers or none of them."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenure = RosterTenureFactory()

    def test_a_picture_without_a_crop_is_not_a_look(self) -> None:
        link = TenureMediaFactory(tenure=self.tenure)
        assert not link.is_look

    def test_a_picture_with_a_crop_is_a_look(self) -> None:
        link = TenureMediaFactory(tenure=self.tenure, crop_x=10, crop_y=0, crop_width=200)
        assert link.is_look

    def test_a_partial_crop_is_refused_by_the_database(self) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TenureMediaFactory(tenure=self.tenure, crop_x=10, crop_y=None, crop_width=200)

    def test_a_zero_width_crop_is_refused_by_the_database(self) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TenureMediaFactory(tenure=self.tenure, crop_x=0, crop_y=0, crop_width=0)


class CharacterArtTests(TestCase):
    """A picture belongs to one tenure or to the character, never both or neither."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenure = RosterTenureFactory()
        cls.entry = cls.tenure.roster_entry

    def test_character_art_belongs_to_the_entry(self) -> None:
        link = TenureMediaFactory(tenure=None, roster_entry=self.entry)
        assert link.is_character_art
        assert not TenureMediaFactory(tenure=self.tenure).is_character_art

    def test_both_owners_are_refused(self) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TenureMediaFactory(tenure=self.tenure, roster_entry=self.entry)

    def test_neither_owner_is_refused(self) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TenureMediaFactory(tenure=None, roster_entry=None)

    def test_the_entry_may_wear_its_own_character_art(self) -> None:
        link = TenureMediaFactory(tenure=None, roster_entry=self.entry)
        self.entry.profile_picture = link
        self.entry.clean()

    def test_the_entry_may_not_wear_another_entrys_character_art(self) -> None:
        other = TenureMediaFactory(tenure=None, roster_entry=RosterEntryFactory())
        self.entry.profile_picture = other
        with self.assertRaises(ValidationError):
            self.entry.clean()


class HiddenCharacterArtTests(TestCase):
    """A tenure hides character art once; only character art of its own entry."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenure = RosterTenureFactory()
        cls.art = TenureMediaFactory(tenure=None, roster_entry=cls.tenure.roster_entry)

    def test_a_tenure_hides_a_picture_once(self) -> None:
        HiddenCharacterArt.objects.create(tenure=self.tenure, picture=self.art)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            HiddenCharacterArt.objects.create(tenure=self.tenure, picture=self.art)

    def test_only_character_art_can_be_hidden(self) -> None:
        own = TenureMediaFactory(tenure=self.tenure)
        with self.assertRaises(ValidationError):
            HiddenCharacterArt(tenure=self.tenure, picture=own).full_clean()

    def test_another_entrys_art_cannot_be_hidden(self) -> None:
        foreign = TenureMediaFactory(tenure=None, roster_entry=RosterEntryFactory())
        with self.assertRaises(ValidationError):
            HiddenCharacterArt(tenure=self.tenure, picture=foreign).full_clean()

    def test_hidden_rows_go_with_their_picture(self) -> None:
        HiddenCharacterArt.objects.create(tenure=self.tenure, picture=self.art)
        TenureMedia.objects.filter(pk=self.art.pk).delete()
        assert not HiddenCharacterArt.objects.exists()
