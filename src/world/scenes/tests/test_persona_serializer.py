from django.test import TestCase

from world.roster.factories import PlayerMediaFactory
from world.scenes.factories import PersonaFactory
from world.scenes.serializers import PersonaSerializer


class PersonaSerializerThumbnailMediaUrlTestCase(TestCase):
    def test_thumbnail_media_url_is_none_when_thumbnail_fk_is_null(self) -> None:
        """thumbnail_media_url is None when Persona.thumbnail FK is not set."""
        persona = PersonaFactory(thumbnail=None)
        data = PersonaSerializer(persona).data
        assert data["thumbnail_media_url"] is None

    def test_thumbnail_media_url_returns_cloudinary_url_when_set(self) -> None:
        """thumbnail_media_url equals Persona.thumbnail.cloudinary_url when set."""
        media = PlayerMediaFactory()
        persona = PersonaFactory(thumbnail=media)
        data = PersonaSerializer(persona).data
        assert data["thumbnail_media_url"] == media.cloudinary_url
