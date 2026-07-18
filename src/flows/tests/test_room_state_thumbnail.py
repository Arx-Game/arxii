"""E2E tests for dynamic thumbnail in room-state payload (#2196).

Tests the full resolution chain from DB state through to the thumbnail_url
field in the serialized room-state payload. Uses serialize_state (the helper
used by the room-state WebSocket payload) directly, since it exercises the
same BaseState.thumbnail_url → resolve_thumbnail path.
"""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import ObjectDisplayData
from flows.factories import SceneDataManagerFactory
from flows.helpers.payloads import serialize_state
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.roster.factories import MediaFactory


class RoomStateThumbnailE2ETest(TestCase):
    """Full resolution chain: DB state → BaseState.thumbnail_url → payload."""

    def setUp(self) -> None:
        self.target = ObjectDBFactory(
            db_key="target",
            db_typeclass_path="typeclasses.characters.Character",
        )
        self.persona_media = MediaFactory()
        ObjectDisplayData.objects.create(object=self.target, thumbnail=self.persona_media)
        self.condition_media = MediaFactory()

    def _target_state(self):
        context = SceneDataManagerFactory()
        return context.initialize_state_for_object(self.target)

    def _thumbnail_url(self) -> str | None:
        state = self._target_state()
        return serialize_state(state).get("thumbnail_url")

    def test_default_thumbnail_shown_when_no_condition(self) -> None:
        """No condition active → state shows ObjectDisplayData thumbnail."""
        url = self._thumbnail_url()
        assert url == self.persona_media.cloudinary_url

    def test_condition_thumbnail_overrides_default(self) -> None:
        """Active condition with thumbnail → state shows condition thumbnail."""
        template = ConditionTemplateFactory(thumbnail=self.condition_media)
        ConditionInstanceFactory(target=self.target, condition=template)

        url = self._thumbnail_url()
        assert url == self.condition_media.cloudinary_url

    def test_thumbnail_reverts_when_condition_removed(self) -> None:
        """Condition cleared → thumbnail falls back to default."""
        template = ConditionTemplateFactory(thumbnail=self.condition_media)
        instance = ConditionInstanceFactory(target=self.target, condition=template)

        url = self._thumbnail_url()
        assert url == self.condition_media.cloudinary_url

        instance.delete()
        url = self._thumbnail_url()
        assert url == self.persona_media.cloudinary_url
