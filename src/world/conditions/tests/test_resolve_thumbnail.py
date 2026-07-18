"""Tests for resolve_thumbnail() — dynamic thumbnail resolution (#2196)."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import ObjectDisplayData
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.thumbnail_services import resolve_thumbnail
from world.roster.factories import MediaFactory


class ResolveThumbnailPriorityTest(TestCase):
    """Tests for the resolve_thumbnail() priority chain."""

    def setUp(self) -> None:
        self.obj = ObjectDBFactory(
            db_key="TestChar",
            db_typeclass_path="typeclasses.characters.Character",
        )
        self.default_media = MediaFactory()
        ObjectDisplayData.objects.create(object=self.obj, thumbnail=self.default_media)

    def test_falls_back_to_object_display_data_when_no_overrides(self) -> None:
        """No persona, no conditions → ObjectDisplayData.thumbnail."""
        url = resolve_thumbnail(self.obj)
        assert url == self.default_media.cloudinary_url

    def test_falls_back_to_none_when_nothing_set(self) -> None:
        """No thumbnail anywhere → None."""
        bare_obj = ObjectDBFactory(db_key="BareObj")
        url = resolve_thumbnail(bare_obj)
        assert url is None

    def test_condition_template_thumbnail_overrides_display_data(self) -> None:
        """Active condition with a thumbnail overrides ObjectDisplayData."""
        condition_media = MediaFactory()
        template = ConditionTemplateFactory(thumbnail=condition_media)
        ConditionInstanceFactory(target=self.obj, condition=template)
        url = resolve_thumbnail(self.obj)
        assert url == condition_media.cloudinary_url

    def test_condition_stage_thumbnail_overrides_template(self) -> None:
        """Stage thumbnail takes priority over template thumbnail."""
        stage_media = MediaFactory()
        template_media = MediaFactory()
        template = ConditionTemplateFactory(
            thumbnail=template_media,
            has_progression=True,
        )
        stage = ConditionStageFactory(condition=template, thumbnail=stage_media)
        ConditionInstanceFactory(target=self.obj, condition=template, current_stage=stage)
        url = resolve_thumbnail(self.obj)
        assert url == stage_media.cloudinary_url

    def test_highest_display_priority_condition_wins(self) -> None:
        """When multiple conditions with thumbnails are active, highest display_priority wins."""
        high_media = MediaFactory()
        low_media = MediaFactory()
        low_pri = ConditionTemplateFactory(
            thumbnail=low_media,
            display_priority=5,
        )
        high_pri = ConditionTemplateFactory(
            thumbnail=high_media,
            display_priority=10,
        )
        ConditionInstanceFactory(target=self.obj, condition=low_pri)
        ConditionInstanceFactory(target=self.obj, condition=high_pri)
        url = resolve_thumbnail(self.obj)
        assert url == high_media.cloudinary_url

    def test_hidden_condition_not_visible_to_non_privileged_viewer(self) -> None:
        """Hidden condition does not override for non-privileged viewers."""
        condition_media = MediaFactory()
        template = ConditionTemplateFactory(
            thumbnail=condition_media,
            is_visible_to_others=False,
        )
        ConditionInstanceFactory(target=self.obj, condition=template)
        url = resolve_thumbnail(self.obj, viewer_can_see_hidden=False)
        assert url == self.default_media.cloudinary_url

    def test_hidden_condition_visible_to_privileged_viewer(self) -> None:
        """A hidden condition overrides for privileged viewers."""
        condition_media = MediaFactory()
        template = ConditionTemplateFactory(
            thumbnail=condition_media,
            is_visible_to_others=False,
        )
        ConditionInstanceFactory(target=self.obj, condition=template)
        url = resolve_thumbnail(self.obj, viewer_can_see_hidden=True)
        assert url == condition_media.cloudinary_url

    def test_fallback_media_used_when_nothing_else_set(self) -> None:
        """fallback_media is the last resort before None."""
        fallback = MediaFactory()
        bare_obj = ObjectDBFactory(db_key="NPC")
        url = resolve_thumbnail(bare_obj, fallback_media=fallback)
        assert url == fallback.cloudinary_url

    def test_cached_conditions_parameter_avoids_extra_query(self) -> None:
        """Passing cached_conditions skips the get_active_conditions query."""
        condition_media = MediaFactory()
        template = ConditionTemplateFactory(thumbnail=condition_media)
        instance = ConditionInstanceFactory(target=self.obj, condition=template)
        url = resolve_thumbnail(self.obj, cached_conditions=[instance])
        assert url == condition_media.cloudinary_url

    def test_condition_without_thumbnail_falls_through(self) -> None:
        """A condition with no thumbnail doesn't block lower-priority sources."""
        template = ConditionTemplateFactory()  # no thumbnail
        ConditionInstanceFactory(target=self.obj, condition=template)
        url = resolve_thumbnail(self.obj)
        assert url == self.default_media.cloudinary_url
