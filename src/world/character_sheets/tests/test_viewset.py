"""
Tests for the character sheets API viewset.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import (
    CharacterSheetFactory,
    GenderFactory,
)
from world.character_sheets.models import Heritage
from world.classes.factories import PathFactory
from world.forms.factories import (
    BuildFactory,
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.forms.models import FormType
from world.progression.factories import CharacterPathHistoryFactory
from world.roster.factories import (
    FamilyFactory,
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.species.factories import SpeciesFactory
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard


class TestCharacterSheetViewSet(TestCase):
    """Tests for CharacterSheetViewSet API endpoints."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create shared test data for all tests in the class."""
        # Original creator: player_number=1
        cls.original_player = PlayerDataFactory()
        cls.roster_entry = RosterEntryFactory()
        # Every roster entry needs a CharacterSheet for the serializer
        CharacterSheetFactory(character=cls.roster_entry.character)
        cls.original_tenure = RosterTenureFactory(
            player_data=cls.original_player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # Second player who picked up the character: player_number=2
        cls.second_player = PlayerDataFactory()
        cls.second_tenure = RosterTenureFactory(
            player_data=cls.second_player,
            roster_entry=cls.roster_entry,
            player_number=2,
        )

        # Staff user
        cls.staff_account = AccountFactory(is_staff=True)

        # Unrelated user (no tenure on this character)
        cls.other_player = PlayerDataFactory()

    def setUp(self) -> None:
        """Set up the API client for each test."""
        self.client = APIClient()

    def test_retrieve_returns_200_for_valid_entry(self) -> None:
        """GET /api/character-sheets/{id}/ returns 200 for an existing roster entry."""
        self.client.force_authenticate(user=self.original_player.account)
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["id"] == self.roster_entry.pk

    def test_retrieve_returns_404_for_nonexistent_entry(self) -> None:
        """GET /api/character-sheets/{id}/ returns 404 for a nonexistent ID."""
        self.client.force_authenticate(user=self.original_player.account)
        url = "/api/character-sheets/999999/"
        response = self.client.get(url)

        assert response.status_code == 404

    def test_can_edit_true_for_original_account(self) -> None:
        """Original creator (player_number=1) gets can_edit=true."""
        self.client.force_authenticate(user=self.original_player.account)
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is True

    def test_can_edit_false_for_second_player(self) -> None:
        """Second player (player_number=2) gets can_edit=false."""
        self.client.force_authenticate(user=self.second_player.account)
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is False

    def test_can_edit_true_for_staff(self) -> None:
        """Staff users get can_edit=true regardless of tenure."""
        self.client.force_authenticate(user=self.staff_account)
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is True

    def test_can_edit_false_for_unrelated_user(self) -> None:
        """A user with no tenure on the character gets can_edit=false."""
        self.client.force_authenticate(user=self.other_player.account)
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is False

    def test_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are rejected."""
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code in (401, 403)

    def test_can_edit_false_when_no_tenures_exist(self) -> None:
        """An entry with no tenures returns can_edit=false for any user."""
        empty_entry = RosterEntryFactory()
        CharacterSheetFactory(character=empty_entry.character)
        self.client.force_authenticate(user=self.original_player.account)
        url = f"/api/character-sheets/{empty_entry.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is False


class TestIdentitySection(TestCase):
    """Tests for the identity section of the character sheet API response."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a fully-populated character for identity tests."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="Alaric")

        cls.gender = GenderFactory(key="male", display_name="Male")
        cls.species = SpeciesFactory(name="Human")
        cls.heritage = Heritage.objects.create(name="Normal")
        cls.family = FamilyFactory(name="Valardin")
        cls.tarot_card = TarotCard.objects.create(
            name="The Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=0,
            latin_name="Stultus",
        )
        cls.realm = RealmFactory(name="Arx")
        cls.build = BuildFactory(name="athletic", display_name="Athletic")

        cls.sheet = CharacterSheetFactory(
            character=cls.character,
            age=25,
            concept="Noble warrior",
            quote="Steel before surrender.",
            gender=cls.gender,
            pronoun_subject="he",
            pronoun_object="him",
            pronoun_possessive="his",
            species=cls.species,
            heritage=cls.heritage,
            family=cls.family,
            tarot_card=cls.tarot_card,
            origin_realm=cls.realm,
            build=cls.build,
            true_height_inches=72,
            additional_desc="Tall and broad-shouldered.",
        )

        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # Create a path history entry
        cls.path = PathFactory(name="Path of Steel")
        cls.path_history = CharacterPathHistoryFactory(
            character=cls.character,
            path=cls.path,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_identity(self) -> dict:
        """Fetch the identity section from the API."""
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["identity"]

    def test_identity_has_all_expected_keys(self) -> None:
        """The identity section contains every specified field."""
        identity = self._get_identity()
        expected_keys = {
            "name",
            "fullname",
            "concept",
            "quote",
            "age",
            "gender",
            "pronouns",
            "species",
            "heritage",
            "family",
            "tarot_card",
            "origin",
            "path",
        }
        assert set(identity.keys()) == expected_keys

    def test_name_is_character_db_key(self) -> None:
        """name comes from the character's db_key."""
        identity = self._get_identity()
        assert identity["name"] == "Alaric"

    def test_fullname_with_family(self) -> None:
        """fullname is 'FirstName FamilyName' when family exists."""
        identity = self._get_identity()
        assert identity["fullname"] == "Alaric Valardin"

    def test_scalar_fields(self) -> None:
        """age, concept, and quote come directly from the sheet."""
        identity = self._get_identity()
        assert identity["age"] == 25
        assert identity["concept"] == "Noble warrior"
        assert identity["quote"] == "Steel before surrender."

    def test_gender_nested(self) -> None:
        """gender is {id, name} from Gender.display_name."""
        identity = self._get_identity()
        assert identity["gender"] == {"id": self.gender.pk, "name": "Male"}

    def test_pronouns_nested(self) -> None:
        """pronouns contain subject, object, possessive from sheet fields."""
        identity = self._get_identity()
        assert identity["pronouns"] == {
            "subject": "he",
            "object": "him",
            "possessive": "his",
        }

    def test_species_nested(self) -> None:
        """species is {id, name}."""
        identity = self._get_identity()
        assert identity["species"] == {"id": self.species.pk, "name": "Human"}

    def test_heritage_nested(self) -> None:
        """heritage is {id, name}."""
        identity = self._get_identity()
        assert identity["heritage"] == {"id": self.heritage.pk, "name": "Normal"}

    def test_family_nested(self) -> None:
        """family is {id, name} when present."""
        identity = self._get_identity()
        assert identity["family"] == {"id": self.family.pk, "name": "Valardin"}

    def test_tarot_card_nested(self) -> None:
        """tarot_card is {id, name} when present."""
        identity = self._get_identity()
        assert identity["tarot_card"] == {"id": self.tarot_card.pk, "name": "The Fool"}

    def test_origin_nested(self) -> None:
        """origin is {id, name} from origin_realm."""
        identity = self._get_identity()
        assert identity["origin"] == {"id": self.realm.pk, "name": "Arx"}

    def test_path_nested(self) -> None:
        """path is {id, name} from latest CharacterPathHistory."""
        identity = self._get_identity()
        assert identity["path"] == {"id": self.path.pk, "name": "Path of Steel"}


class TestIdentityNullableFields(TestCase):
    """Tests for nullable/optional fields in the identity section."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a minimal character with nullable fields left null."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="Orphan")

        cls.sheet = CharacterSheetFactory(
            character=cls.character,
            family=None,
            tarot_card=None,
            origin_realm=None,
            gender=None,
            species=None,
            heritage=None,
        )

        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_identity(self) -> dict:
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["identity"]

    def test_fullname_without_family(self) -> None:
        """Without a family, fullname equals the character name."""
        identity = self._get_identity()
        assert identity["fullname"] == "Orphan"

    def test_family_null(self) -> None:
        """family is null when character has no family."""
        identity = self._get_identity()
        assert identity["family"] is None

    def test_tarot_card_null(self) -> None:
        """tarot_card is null when not set."""
        identity = self._get_identity()
        assert identity["tarot_card"] is None

    def test_origin_null(self) -> None:
        """origin is null when origin_realm is not set."""
        identity = self._get_identity()
        assert identity["origin"] is None

    def test_path_null_when_no_history(self) -> None:
        """path is null when no CharacterPathHistory exists."""
        identity = self._get_identity()
        assert identity["path"] is None

    def test_gender_null(self) -> None:
        """gender is null when not set."""
        identity = self._get_identity()
        assert identity["gender"] is None

    def test_species_null(self) -> None:
        """species is null when not set."""
        identity = self._get_identity()
        assert identity["species"] is None

    def test_heritage_null(self) -> None:
        """heritage is null when not set."""
        identity = self._get_identity()
        assert identity["heritage"] is None


class TestAppearanceSection(TestCase):
    """Tests for the appearance section of the character sheet API response."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with appearance data and form traits."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="Zara")
        cls.build = BuildFactory(name="slender", display_name="Slender")

        cls.sheet = CharacterSheetFactory(
            character=cls.character,
            true_height_inches=65,
            build=cls.build,
            additional_desc="Lithe and graceful.",
        )

        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # Create TRUE form with trait values
        cls.true_form = CharacterFormFactory(
            character=cls.character,
            form_type=FormType.TRUE,
        )
        hair_trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        hair_option = FormTraitOptionFactory(trait=hair_trait, name="black", display_name="Black")
        eye_trait = FormTraitFactory(name="eye_color", display_name="Eye Color")
        eye_option = FormTraitOptionFactory(trait=eye_trait, name="green", display_name="Green")
        CharacterFormValueFactory(form=cls.true_form, trait=hair_trait, option=hair_option)
        CharacterFormValueFactory(form=cls.true_form, trait=eye_trait, option=eye_option)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_appearance(self) -> dict:
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["appearance"]

    def test_appearance_has_all_expected_keys(self) -> None:
        """The appearance section contains every specified field."""
        appearance = self._get_appearance()
        expected_keys = {"height_inches", "build", "description", "form_traits"}
        assert set(appearance.keys()) == expected_keys

    def test_height_inches(self) -> None:
        """height_inches comes from true_height_inches."""
        appearance = self._get_appearance()
        assert appearance["height_inches"] == 65

    def test_build_nested(self) -> None:
        """build is {id, name} from Build.display_name."""
        appearance = self._get_appearance()
        assert appearance["build"] == {"id": self.build.pk, "name": "Slender"}

    def test_description(self) -> None:
        """description comes from additional_desc."""
        appearance = self._get_appearance()
        assert appearance["description"] == "Lithe and graceful."

    def test_form_traits_content(self) -> None:
        """form_traits lists trait/value pairs from the TRUE form."""
        appearance = self._get_appearance()
        traits = appearance["form_traits"]
        assert len(traits) == 2
        trait_map = {t["trait"]: t["value"] for t in traits}
        assert trait_map["Hair Color"] == "Black"
        assert trait_map["Eye Color"] == "Green"


class TestAppearanceNoTrueForm(TestCase):
    """Tests for appearance section when no TRUE form exists."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character without a TRUE form."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="Blank")

        cls.sheet = CharacterSheetFactory(
            character=cls.character,
            true_height_inches=None,
            build=None,
            additional_desc="",
        )

        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_appearance(self) -> dict:
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["appearance"]

    def test_form_traits_empty_when_no_true_form(self) -> None:
        """form_traits is an empty list when no TRUE form exists."""
        appearance = self._get_appearance()
        assert appearance["form_traits"] == []

    def test_height_inches_null(self) -> None:
        """height_inches is null when not set."""
        appearance = self._get_appearance()
        assert appearance["height_inches"] is None

    def test_build_null(self) -> None:
        """build is null when not set."""
        appearance = self._get_appearance()
        assert appearance["build"] is None

    def test_description_empty(self) -> None:
        """description is an empty string when not set."""
        appearance = self._get_appearance()
        assert appearance["description"] == ""
