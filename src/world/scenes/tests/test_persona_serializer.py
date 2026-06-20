from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.consent.factories import SocialConsentPreferenceFactory
from world.roster.factories import PlayerMediaFactory, RosterEntryFactory, RosterTenureFactory
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


class PersonaSerializerAllowSocialActionsTestCase(TestCase):
    """allow_social_actions mirrors the challenge consent gate for the scene UI (#1181)."""

    def _persona_with_tenure(self) -> tuple:
        sheet = CharacterSheetFactory()
        persona = PersonaFactory(character_sheet=sheet)
        entry = RosterEntryFactory(character_sheet=sheet)
        tenure = RosterTenureFactory(roster_entry=entry)
        return persona, tenure

    def test_defaults_true_without_tenure(self) -> None:
        """A persona whose character has no active tenure is targetable by default."""
        persona = PersonaFactory()
        data = PersonaSerializer(persona).data
        assert data["allow_social_actions"] is True

    def test_true_when_tenure_has_no_preference(self) -> None:
        """No SocialConsentPreference row → allow (default)."""
        persona, _tenure = self._persona_with_tenure()
        data = PersonaSerializer(persona).data
        assert data["allow_social_actions"] is True

    def test_true_when_preference_allows(self) -> None:
        persona, tenure = self._persona_with_tenure()
        SocialConsentPreferenceFactory(tenure=tenure, allow_social_actions=True)
        data = PersonaSerializer(persona).data
        assert data["allow_social_actions"] is True

    def test_false_when_preference_opts_out(self) -> None:
        """allow_social_actions=False on the active tenure → not targetable."""
        persona, tenure = self._persona_with_tenure()
        SocialConsentPreferenceFactory(tenure=tenure, allow_social_actions=False)
        data = PersonaSerializer(persona).data
        assert data["allow_social_actions"] is False
