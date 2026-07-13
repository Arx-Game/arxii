"""Tests for thumbnail FK field on AlternateSelf (#2196)."""

from django.test import TestCase

from world.forms.factories import AlternateSelfFactory
from world.roster.factories import PlayerMediaFactory


class AlternateSelfThumbnailTest(TestCase):
    def test_thumbnail_defaults_to_none(self) -> None:
        """New AlternateSelf has no thumbnail by default."""
        alt_self = AlternateSelfFactory()
        assert alt_self.thumbnail is None

    def test_thumbnail_can_be_set(self) -> None:
        """A PlayerMedia can be attached as the alt-self thumbnail."""
        media = PlayerMediaFactory()
        alt_self = AlternateSelfFactory(thumbnail=media)
        alt_self.refresh_from_db()
        assert alt_self.thumbnail == media
        assert alt_self.thumbnail.cloudinary_url == media.cloudinary_url
