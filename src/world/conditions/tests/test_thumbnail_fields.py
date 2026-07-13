"""Tests for thumbnail FK fields on ConditionTemplate and ConditionStage (#2196)."""

from django.test import TestCase

from world.conditions.factories import (
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.roster.factories import PlayerMediaFactory


class ConditionTemplateThumbnailTest(TestCase):
    def test_thumbnail_defaults_to_none(self) -> None:
        """New ConditionTemplate has no thumbnail by default."""
        template = ConditionTemplateFactory()
        assert template.thumbnail is None

    def test_thumbnail_can_be_set(self) -> None:
        """A PlayerMedia can be attached as the thumbnail."""
        media = PlayerMediaFactory()
        template = ConditionTemplateFactory(thumbnail=media)
        template.refresh_from_db()
        assert template.thumbnail == media
        assert template.thumbnail.cloudinary_url == media.cloudinary_url


class ConditionStageThumbnailTest(TestCase):
    def test_thumbnail_defaults_to_none(self) -> None:
        """New ConditionStage has no thumbnail by default."""
        stage = ConditionStageFactory()
        assert stage.thumbnail is None

    def test_thumbnail_can_be_set(self) -> None:
        """A PlayerMedia can be attached as the stage thumbnail."""
        media = PlayerMediaFactory()
        stage = ConditionStageFactory(thumbnail=media)
        stage.refresh_from_db()
        assert stage.thumbnail == media
