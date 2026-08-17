from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.services import create_character_with_sheet
from world.consent.factories import SocialConsentPreferenceFactory
from world.roster.constants import MembershipBasis
from world.roster.factories import (
    FamilyFactory,
    KinspersonFactory,
    MediaFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.roster.models import Family
from world.roster.services.kinship import add_membership
from world.scenes.factories import PersonaFactory
from world.scenes.models import PersonaType
from world.scenes.serializers import PersonaSerializer
from world.societies.factories import OrganizationFactory
from world.societies.houses.constants import NameDegree
from world.societies.houses.models import NobiliaryParticle


class PersonaSerializerThumbnailMediaUrlTestCase(TestCase):
    def test_thumbnail_media_url_is_none_when_thumbnail_fk_is_null(self) -> None:
        """thumbnail_media_url is None when Persona.thumbnail FK is not set."""
        persona = PersonaFactory(thumbnail=None)
        data = PersonaSerializer(persona).data
        assert data["thumbnail_media_url"] is None

    def test_thumbnail_media_url_returns_cloudinary_url_when_set(self) -> None:
        """thumbnail_media_url equals Persona.thumbnail.cloudinary_url when set."""
        media = MediaFactory()
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


class PersonaSerializerDisplayNameTestCase(TestCase):
    """#3261 — display_name derives the particled name for PRIMARY personas only."""

    def _housed_primary(self):
        _character, sheet, persona = create_character_with_sheet(
            character_key="Sharlotte Regente",
            primary_persona_name="Sharlotte Regente",
        )
        family = FamilyFactory(name="Regente", family_type=Family.FamilyType.NOBLE)
        org = OrganizationFactory(name="House Regente", family=family)
        NobiliaryParticle.objects.create(
            realm=org.society.realm,
            family_type=Family.FamilyType.NOBLE,
            particle="du",
            taken_in_particle="dau",
        )
        person = KinspersonFactory(name="Sharlotte Regente", sheet=sheet)
        add_membership(kinsperson=person, family=family, basis=MembershipBasis.BORN)
        return persona

    def test_primary_persona_renders_particled_common_form(self) -> None:
        persona = self._housed_primary()
        data = PersonaSerializer(persona).data
        assert data["display_name"] == "Sharlotte du Regente"

    def test_degree_preference_is_honored(self) -> None:
        persona = self._housed_primary()
        persona.name_degree = NameDegree.FAMILIAR
        persona.save(update_fields=["name_degree"])
        data = PersonaSerializer(persona).data
        assert data["display_name"] == "Sharlotte"

    def test_disguise_presents_claimed_name_bare(self) -> None:
        """A non-primary face never leaks the kinship-derived name (#3261)."""
        primary = self._housed_primary()
        mask = PersonaFactory(
            character_sheet=primary.character_sheet,
            persona_type=PersonaType.TEMPORARY,
            name="Mysterious Stranger",
            is_fake_name=True,
        )
        data = PersonaSerializer(mask).data
        assert data["display_name"] == "Mysterious Stranger"
