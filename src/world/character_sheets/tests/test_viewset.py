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
from world.classes.models import PathStage
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
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
from world.skills.factories import (
    CharacterSkillValueFactory,
    CharacterSpecializationValueFactory,
    SkillFactory,
    SpecializationFactory,
)
from world.species.factories import SpeciesFactory
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard
from world.traits.factories import CharacterTraitValueFactory, StatTraitFactory
from world.traits.models import TraitCategory


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


class TestStatsSection(TestCase):
    """Tests for the stats section of the character sheet API response."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with stat trait values."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="StatChar")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # Create stat traits and values
        cls.strength_trait = StatTraitFactory(name="strength", category=TraitCategory.PHYSICAL)
        cls.agility_trait = StatTraitFactory(name="agility", category=TraitCategory.PHYSICAL)
        CharacterTraitValueFactory(character=cls.character, trait=cls.strength_trait, value=30)
        CharacterTraitValueFactory(character=cls.character, trait=cls.agility_trait, value=40)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_stats(self) -> dict:
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["stats"]

    def test_stats_contains_expected_values(self) -> None:
        """Stats section maps stat names to their values."""
        stats = self._get_stats()
        assert stats["strength"] == 30
        assert stats["agility"] == 40

    def test_stats_only_contains_stat_traits(self) -> None:
        """Stats section only contains traits with trait_type='stat', not skills."""
        stats = self._get_stats()
        assert len(stats) == 2


class TestStatsEmpty(TestCase):
    """Tests for the stats section when no stats exist."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with no stat values."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="NoStats")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_stats_empty_dict_when_no_stats(self) -> None:
        """Stats section is an empty dict when no stat values exist."""
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["stats"] == {}


class TestSkillsSection(TestCase):
    """Tests for the skills section of the character sheet API response."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with skills and specializations."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="SkillChar")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # Create a skill with a specialization
        cls.melee_skill = SkillFactory(trait__name="Melee", trait__category=TraitCategory.COMBAT)
        cls.swords_spec = SpecializationFactory(name="Swords", parent_skill=cls.melee_skill)
        CharacterSkillValueFactory(character=cls.character, skill=cls.melee_skill, value=30)
        CharacterSpecializationValueFactory(
            character=cls.character, specialization=cls.swords_spec, value=10
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_skills(self) -> list:
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["skills"]

    def test_skills_contains_skill_entry(self) -> None:
        """Skills section contains the character's skill."""
        skills = self._get_skills()
        assert len(skills) == 1

    def test_skill_entry_structure(self) -> None:
        """Each skill entry has {skill: {id, name, category}, value, specializations}."""
        skills = self._get_skills()
        entry = skills[0]
        assert set(entry.keys()) == {"skill", "value", "specializations"}
        assert set(entry["skill"].keys()) == {"id", "name", "category"}

    def test_skill_entry_values(self) -> None:
        """Skill entry contains correct id, name, category, and value."""
        skills = self._get_skills()
        entry = skills[0]
        assert entry["skill"]["id"] == self.melee_skill.pk
        assert entry["skill"]["name"] == "Melee"
        assert entry["skill"]["category"] == TraitCategory.COMBAT
        assert entry["value"] == 30

    def test_skill_specializations(self) -> None:
        """Skill entry contains nested specializations with id, name, value."""
        skills = self._get_skills()
        entry = skills[0]
        specs = entry["specializations"]
        assert len(specs) == 1
        assert specs[0]["id"] == self.swords_spec.pk
        assert specs[0]["name"] == "Swords"
        assert specs[0]["value"] == 10


class TestSkillsEmpty(TestCase):
    """Tests for the skills section when no skills exist."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with no skill values."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="NoSkills")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_skills_empty_list_when_no_skills(self) -> None:
        """Skills section is an empty list when no skill values exist."""
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["skills"] == []


class TestPathDetailSection(TestCase):
    """Tests for the top-level path detail section of the character sheet."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with multiple path history entries."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="PathWalker")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # Create two paths at different stages
        cls.prospect_path = PathFactory(
            name="Path of Steel",
            stage=PathStage.PROSPECT,
        )
        cls.potential_path = PathFactory(
            name="Vanguard",
            stage=PathStage.POTENTIAL,
        )

        # Create history entries (potential is later/higher stage)
        cls.history_1 = CharacterPathHistoryFactory(
            character=cls.character,
            path=cls.prospect_path,
        )
        cls.history_2 = CharacterPathHistoryFactory(
            character=cls.character,
            path=cls.potential_path,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_path(self) -> dict | None:
        """Fetch the path section from the API."""
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["path"]

    def test_path_not_none_when_history_exists(self) -> None:
        """Path section is not null when path history exists."""
        path = self._get_path()
        assert path is not None

    def test_path_has_expected_keys(self) -> None:
        """Path section contains id, name, stage, tier, and history."""
        path = self._get_path()
        expected_keys = {"id", "name", "stage", "tier", "history"}
        assert set(path.keys()) == expected_keys

    def test_path_shows_latest_path(self) -> None:
        """Path section shows the most recent (highest stage) path as current.

        The prefetch orders by ``-selected_at`` so the newest entry is first.
        With auto_now_add, the second-created entry (Vanguard) is newest.
        """
        path = self._get_path()
        assert path["name"] == "Vanguard"
        assert path["id"] == self.potential_path.pk

    def test_path_stage_and_tier(self) -> None:
        """Path section includes stage number and human-readable tier label."""
        path = self._get_path()
        assert path["stage"] == PathStage.POTENTIAL
        assert path["tier"] == "Potential"

    def test_path_history_list(self) -> None:
        """History contains entries for all paths with path, stage, tier, date."""
        path = self._get_path()
        history = path["history"]
        assert len(history) == 2
        # Each entry should have the expected keys
        for entry in history:
            assert set(entry.keys()) == {"path", "stage", "tier", "date"}

    def test_path_history_entry_values(self) -> None:
        """History entries contain correct path names and stage info."""
        path = self._get_path()
        history = path["history"]
        names = {entry["path"] for entry in history}
        assert "Path of Steel" in names
        assert "Vanguard" in names


class TestPathDetailNull(TestCase):
    """Tests for the path section when no path history exists."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with no path history."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="NoPath")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_path_is_null_when_no_history(self) -> None:
        """Path section is null when no CharacterPathHistory entries exist."""
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["path"] is None


class TestDistinctionsSection(TestCase):
    """Tests for the distinctions section of the character sheet."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with distinctions."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="DistChar")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # Create distinctions
        cls.distinction_a = DistinctionFactory(name="Misbegotten")
        cls.distinction_b = DistinctionFactory(name="Strong Arm", max_rank=3)

        cls.cd_a = CharacterDistinctionFactory(
            character=cls.character,
            distinction=cls.distinction_a,
            rank=1,
            notes="Born outside the compact.",
        )
        cls.cd_b = CharacterDistinctionFactory(
            character=cls.character,
            distinction=cls.distinction_b,
            rank=2,
            notes="",
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_distinctions(self) -> list:
        """Fetch the distinctions section from the API."""
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["distinctions"]

    def test_distinctions_returns_correct_count(self) -> None:
        """Distinctions section returns all character distinctions."""
        distinctions = self._get_distinctions()
        assert len(distinctions) == 2

    def test_distinction_entry_keys(self) -> None:
        """Each distinction entry has id, name, rank, notes."""
        distinctions = self._get_distinctions()
        for entry in distinctions:
            assert set(entry.keys()) == {"id", "name", "rank", "notes"}

    def test_distinction_entry_values(self) -> None:
        """Distinction entries contain correct values from the models."""
        distinctions = self._get_distinctions()
        by_name = {d["name"]: d for d in distinctions}

        misbegotten = by_name["Misbegotten"]
        assert misbegotten["id"] == self.cd_a.pk
        assert misbegotten["rank"] == 1
        assert misbegotten["notes"] == "Born outside the compact."

        strong_arm = by_name["Strong Arm"]
        assert strong_arm["id"] == self.cd_b.pk
        assert strong_arm["rank"] == 2
        assert strong_arm["notes"] == ""


class TestDistinctionsEmpty(TestCase):
    """Tests for the distinctions section when no distinctions exist."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with no distinctions."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="NoDist")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_distinctions_empty_list_when_none(self) -> None:
        """Distinctions section is an empty list when character has none."""
        url = f"/api/character-sheets/{self.roster_entry.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["distinctions"] == []
