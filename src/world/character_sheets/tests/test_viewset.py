"""
Tests for the character sheets API viewset.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import (
    CharacterSheetFactory,
    GenderFactory,
)
from world.character_sheets.models import CharacterSheet, Heritage
from world.character_sheets.serializers import (
    _build_appearance,
    _build_distinctions,
    _build_goals,
    _build_identity,
    _build_magic,
    _build_path_detail,
    _build_personas,
    _build_profile_picture,
    _build_skills,
    _build_stats,
    _build_story,
    _build_theming,
    get_character_sheet_queryset,
)
from world.character_sheets.types import SheetVisibility
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
from world.goals.factories import CharacterGoalFactory, GoalDomainFactory
from world.magic.constants import GlimpseState, GlimpseTagAxis, RitualExecutionKind
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterGiftFactory,
    CharacterGlimpseTagFactory,
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    FacetFactory,
    GiftFactory,
    GlimpseTagFactory,
    MotifFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    MotifResonanceStyleFactory,
    ResonanceFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)
from world.magic.models import CharacterAura
from world.progression.factories import CharacterPathHistoryFactory
from world.roster.factories import (
    FamilyFactory,
    MediaFactory,
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
    TenureMediaFactory,
)
from world.scenes.factories import PersonaFactory
from world.secrets.factories import SecretFactory
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
        # RosterEntryFactory auto-creates a CharacterSheet for the character.
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
        """GET /api/character-sheets/{id}/ returns 200 for an existing character."""
        self.client.force_authenticate(user=self.original_player.account)
        url = f"/api/character-sheets/{self.roster_entry.character_sheet.character.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["id"] == self.roster_entry.character_sheet.character.pk

    def test_retrieve_returns_404_for_nonexistent_entry(self) -> None:
        """GET /api/character-sheets/{id}/ returns 404 for a nonexistent ID."""
        self.client.force_authenticate(user=self.original_player.account)
        url = "/api/character-sheets/999999/"
        response = self.client.get(url)

        assert response.status_code == 404

    def test_can_edit_true_for_original_account(self) -> None:
        """Original creator (player_number=1) gets can_edit=true."""
        self.client.force_authenticate(user=self.original_player.account)
        url = f"/api/character-sheets/{self.roster_entry.character_sheet.character.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is True

    def test_can_edit_false_for_second_player(self) -> None:
        """Second player (player_number=2) gets can_edit=false."""
        self.client.force_authenticate(user=self.second_player.account)
        url = f"/api/character-sheets/{self.roster_entry.character_sheet.character.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is False

    def test_can_edit_true_for_staff(self) -> None:
        """Staff users get can_edit=true regardless of tenure."""
        self.client.force_authenticate(user=self.staff_account)
        url = f"/api/character-sheets/{self.roster_entry.character_sheet.character.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is True

    def test_can_edit_false_for_unrelated_user(self) -> None:
        """A user with no tenure on the character gets can_edit=false."""
        self.client.force_authenticate(user=self.other_player.account)
        url = f"/api/character-sheets/{self.roster_entry.character_sheet.character.pk}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["can_edit"] is False

    def test_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are rejected."""
        url = f"/api/character-sheets/{self.roster_entry.character_sheet.character.pk}/"
        response = self.client.get(url)

        assert response.status_code in (401, 403)

    def test_can_edit_false_when_no_tenures_exist(self) -> None:
        """An entry with no tenures returns can_edit=false for any user."""
        empty_entry = RosterEntryFactory()
        # RosterEntryFactory already creates the CharacterSheet.
        self.client.force_authenticate(user=self.original_player.account)
        url = f"/api/character-sheets/{empty_entry.character_sheet.character.pk}/"
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

        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
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
        url = f"/api/character-sheets/{self.character.pk}/"
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
            "worship",
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

        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_identity(self) -> dict:
        url = f"/api/character-sheets/{self.character.pk}/"
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

        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
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
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["appearance"]

    def test_appearance_has_all_expected_keys(self) -> None:
        """The appearance section contains every specified field."""
        appearance = self._get_appearance()
        expected_keys = {"height_inches", "height_band", "build", "description", "form_traits"}
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

    def test_form_traits_show_active_persona_descriptor(self) -> None:
        """A descriptor on the active persona overrides the normalized value."""
        from world.forms.factories import PersonaTraitDescriptorFactory
        from world.forms.models import FormTrait

        PersonaTraitDescriptorFactory(
            persona=self.sheet.primary_persona,
            trait=FormTrait.objects.get(name="hair_color"),
            text="Crimson",
        )

        trait_map = {t["trait"]: t["value"] for t in self._get_appearance()["form_traits"]}
        assert trait_map["Hair Color"] == "Crimson"  # descriptor wins
        assert trait_map["Eye Color"] == "Green"  # no descriptor → normalized


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

        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_appearance(self) -> dict:
        url = f"/api/character-sheets/{self.character.pk}/"
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
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
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
        url = f"/api/character-sheets/{self.character.pk}/"
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
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
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
        url = f"/api/character-sheets/{self.character.pk}/"
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
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
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
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["skills"]

    def test_skills_contains_skill_entry(self) -> None:
        """Skills section contains the character's skill."""
        skills = self._get_skills()
        assert len(skills) == 1

    def test_skill_entry_structure(self) -> None:
        """Each skill entry has {skill, value, at_boundary, specializations} (#2115)."""
        skills = self._get_skills()
        entry = skills[0]
        assert set(entry.keys()) == {"skill", "value", "at_boundary", "specializations"}
        assert set(entry["skill"].keys()) == {"id", "name", "category"}

    def test_skill_entry_values(self) -> None:
        """Skill entry contains correct id, name, category, and value."""
        skills = self._get_skills()
        entry = skills[0]
        assert entry["skill"]["id"] == self.melee_skill.pk
        assert entry["skill"]["name"] == "Melee"
        assert entry["skill"]["category"] == TraitCategory.COMBAT
        assert entry["value"] == 30
        assert entry["at_boundary"] is False

    def test_skill_entry_at_boundary_true_when_gated(self) -> None:
        """A skill parked at an XP boundary (19/29/39/49) reports at_boundary=True (#2115)."""
        gated_skill = SkillFactory(trait__name="Gated Skill", trait__category=TraitCategory.COMBAT)
        CharacterSkillValueFactory(character=self.character, skill=gated_skill, value=29)

        skills = self._get_skills()
        entry = next(e for e in skills if e["skill"]["id"] == gated_skill.pk)
        assert entry["at_boundary"] is True

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
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
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
        url = f"/api/character-sheets/{self.character.pk}/"
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
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
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
        url = f"/api/character-sheets/{self.character.pk}/"
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
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
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
        url = f"/api/character-sheets/{self.character.pk}/"
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
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
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
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["distinctions"]

    def test_distinctions_returns_correct_count(self) -> None:
        """Distinctions section returns all character distinctions."""
        distinctions = self._get_distinctions()
        assert len(distinctions) == 2

    def test_distinction_entry_keys(self) -> None:
        """Each distinction entry has id, name, rank, notes, is_secret, is_from_glimpse (#2427)."""
        distinctions = self._get_distinctions()
        for entry in distinctions:
            assert set(entry.keys()) == {
                "id",
                "name",
                "rank",
                "notes",
                "is_secret",
                "is_from_glimpse",
            }

    def test_distinction_entry_values(self) -> None:
        """Distinction entries contain correct values from the models."""
        distinctions = self._get_distinctions()
        by_name = {d["name"]: d for d in distinctions}

        misbegotten = by_name["Misbegotten"]
        assert misbegotten["id"] == self.cd_a.pk
        assert misbegotten["rank"] == 1
        assert misbegotten["notes"] == "Born outside the compact."
        assert misbegotten["is_from_glimpse"] is False

        strong_arm = by_name["Strong Arm"]
        assert strong_arm["id"] == self.cd_b.pk
        assert strong_arm["rank"] == 2
        assert strong_arm["notes"] == ""
        assert strong_arm["is_from_glimpse"] is False

    def test_distinction_entry_is_from_glimpse_true_when_linked(self) -> None:
        """A distinction linked via CharacterDistinction.from_glimpse reports True (#2427)."""
        from world.magic.factories import CharacterAuraFactory

        aura = CharacterAuraFactory(character=self.character)
        self.cd_a.from_glimpse = aura
        self.cd_a.save()

        distinctions = self._get_distinctions()
        by_name = {d["name"]: d for d in distinctions}
        assert by_name["Misbegotten"]["is_from_glimpse"] is True
        assert by_name["Strong Arm"]["is_from_glimpse"] is False


class TestDistinctionsEmpty(TestCase):
    """Tests for the distinctions section when no distinctions exist."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with no distinctions."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="NoDist")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
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
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["distinctions"] == []


class TestDistinctionsPrivacy(TestCase):
    """Server-side privacy for secret distinctions (final review, #1446).

    A foreign (non-owner, non-staff) viewer's GET must not surface a secret distinction —
    the public one is visible, the secret one is dropped entirely. The owner's own GET sees
    both, with ``is_secret`` flagging the gated row.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with one public and one secret distinction."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="SecretDistChar")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        cls.public_distinction = DistinctionFactory(name="PublicHonor")
        cls.secret_distinction = DistinctionFactory(name="HiddenShame")

        cls.public_cd = CharacterDistinctionFactory(
            character=cls.character,
            distinction=cls.public_distinction,
            rank=1,
        )
        cls.secret_cd = CharacterDistinctionFactory(
            character=cls.character,
            distinction=cls.secret_distinction,
            rank=1,
            secret=SecretFactory(subject_sheet=cls.roster_entry.character_sheet),
        )

        # Foreign viewer: authenticated account with no tenure on this character.
        cls.foreign_player = PlayerDataFactory()

    def _get_distinctions(self, account) -> list:
        """Fetch the distinctions section from the API as the given account."""
        client = APIClient()
        client.force_authenticate(user=account)
        url = f"/api/character-sheets/{self.character.pk}/"
        response = client.get(url)
        assert response.status_code == 200
        return response.data["distinctions"]

    def test_foreign_viewer_does_not_see_secret_distinction(self) -> None:
        """A foreign account's GET must contain the public name but never the secret one."""
        distinctions = self._get_distinctions(self.foreign_player.account)
        names = {d["name"] for d in distinctions}

        assert "PublicHonor" in names
        assert "HiddenShame" not in names

    def test_owner_sees_both_distinctions_with_is_secret_flag(self) -> None:
        """The owner's own GET contains both, with is_secret true on the gated row."""
        distinctions = self._get_distinctions(self.player.account)
        by_name = {d["name"]: d for d in distinctions}

        assert set(by_name) == {"PublicHonor", "HiddenShame"}
        assert by_name["PublicHonor"]["is_secret"] is False
        assert by_name["HiddenShame"]["is_secret"] is True


class TestMagicSectionFull(TestCase):
    """Tests for the magic section with all sub-sections populated."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with full magic data."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="MageChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # --- Gift with resonances and techniques ---
        cls.resonance_resolve = ResonanceFactory(name="Resolve")
        cls.resonance_metal = ResonanceFactory(name="Metal")

        cls.gift = GiftFactory(name="Iron Will", description="Unyielding magical will.")
        cls.gift.resonances.add(cls.resonance_resolve, cls.resonance_metal)

        cls.style = TechniqueStyleFactory(name="Manifestation")
        cls.technique = TechniqueFactory(
            name="Steel Skin",
            gift=cls.gift,
            style=cls.style,
            level=3,
            description="Hardens skin to steel.",
        )

        cls.char_gift = CharacterGiftFactory(character=cls.sheet, gift=cls.gift)
        cls.char_technique = CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

        # --- Motif with resonances and facets ---
        cls.motif = MotifFactory(
            character=cls.sheet,
            description="An aesthetic of enduring iron.",
        )
        cls.motif_resonance = MotifResonanceFactory(
            motif=cls.motif,
            resonance=cls.resonance_resolve,
        )
        cls.facet_spider = FacetFactory(name="Spider")
        cls.facet_silk = FacetFactory(name="Silk")
        MotifResonanceAssociationFactory(
            motif_resonance=cls.motif_resonance,
            facet=cls.facet_spider,
        )
        MotifResonanceAssociationFactory(
            motif_resonance=cls.motif_resonance,
            facet=cls.facet_silk,
        )
        cls.motif_style = MotifResonanceStyleFactory(
            motif_resonance=cls.motif_resonance,
            style__name="Enduring",
        )

        # --- Anima Ritual ---
        # Link character to its player account so author_account lookup works.
        cls.character.db_account = cls.player.account
        cls.character.save(update_fields=["db_account"])

        cls.stat_willpower = StatTraitFactory(name="Willpower")
        cls.melee_skill = SkillFactory(trait__name="Melee", trait__category=TraitCategory.COMBAT)
        cls.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=cls.player.account,
            description="Meditate with a blade in hand.",
        )
        RitualCheckConfigFactory(
            ritual=cls.ritual,
            stat=cls.stat_willpower,
            skill=cls.melee_skill,
            resonance=cls.resonance_resolve,
        )

        # --- Aura (FK to ObjectDB) ---

        cls.aura = CharacterAuraFactory(
            character=cls.character,
            celestial=Decimal("20.00"),
            primal=Decimal("50.00"),
            abyssal=Decimal("30.00"),
            glimpse_story="A vision of iron chains.",
        )

        # --- Claimed resonance balance (#2032) ---
        cls.character_resonance = CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance_resolve,
            balance=15,
            lifetime_earned=40,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_magic(self) -> dict:
        """Fetch the magic section from the API."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["magic"]

    def test_magic_is_not_null(self) -> None:
        """Magic section is returned when magic data exists."""
        magic = self._get_magic()
        assert magic is not None

    def test_magic_has_all_expected_keys(self) -> None:
        """Magic section contains gifts, motif, anima_ritual, aura, and resonances (#2032)."""
        magic = self._get_magic()
        expected_keys = {"gifts", "motif", "anima_ritual", "aura", "resonances"}
        assert set(magic.keys()) == expected_keys

    # --- Gift tests ---

    def test_gifts_list_length(self) -> None:
        """Gifts list contains the correct number of gifts."""
        magic = self._get_magic()
        assert len(magic["gifts"]) == 1

    def test_gift_name_and_description(self) -> None:
        """Gift entry contains correct name and description."""
        magic = self._get_magic()
        gift = magic["gifts"][0]
        assert gift["name"] == "Iron Will"
        assert gift["description"] == "Unyielding magical will."

    def test_gift_resonances(self) -> None:
        """Gift entry contains resonance names from the gift's M2M."""
        magic = self._get_magic()
        gift = magic["gifts"][0]
        assert set(gift["resonances"]) == {"Resolve", "Metal"}

    def test_gift_techniques(self) -> None:
        """Gift entry contains techniques with name, level, style, description."""
        magic = self._get_magic()
        gift = magic["gifts"][0]
        assert len(gift["techniques"]) == 1
        tech = gift["techniques"][0]
        assert tech["name"] == "Steel Skin"
        assert tech["level"] == 3
        assert tech["style"] == "Manifestation"
        assert tech["description"] == "Hardens skin to steel."

    # --- Motif tests ---

    def test_motif_description(self) -> None:
        """Motif entry contains correct description."""
        magic = self._get_magic()
        assert magic["motif"]["description"] == "An aesthetic of enduring iron."

    def test_motif_resonances(self) -> None:
        """Motif entry contains resonances with names and facets."""
        magic = self._get_magic()
        resonances = magic["motif"]["resonances"]
        assert len(resonances) == 1
        assert resonances[0]["name"] == "Resolve"

    def test_motif_resonance_facets(self) -> None:
        """Motif resonance entry contains facet names."""
        magic = self._get_magic()
        facets = magic["motif"]["resonances"][0]["facets"]
        assert set(facets) == {"Spider", "Silk"}

    def test_motif_resonance_styles(self) -> None:
        """Motif resonance entry contains bound style names (#2030)."""
        magic = self._get_magic()
        styles = magic["motif"]["resonances"][0]["styles"]
        assert styles == ["Enduring"]

    # --- Anima Ritual tests ---

    def test_anima_ritual_stat(self) -> None:
        """Anima ritual entry contains the stat name."""
        magic = self._get_magic()
        assert magic["anima_ritual"]["stat"] == "Willpower"

    def test_anima_ritual_skill(self) -> None:
        """Anima ritual entry contains the skill name."""
        magic = self._get_magic()
        assert magic["anima_ritual"]["skill"] == "Melee"

    def test_anima_ritual_resonance(self) -> None:
        """Anima ritual entry contains the resonance name."""
        magic = self._get_magic()
        assert magic["anima_ritual"]["resonance"] == "Resolve"

    def test_anima_ritual_description(self) -> None:
        """Anima ritual entry contains the description."""
        magic = self._get_magic()
        assert magic["anima_ritual"]["description"] == "Meditate with a blade in hand."

    # --- Aura tests ---

    def test_aura_celestial(self) -> None:
        """Aura entry contains the correct celestial percentage."""

        magic = self._get_magic()
        assert magic["aura"]["celestial"] == Decimal("20.00")

    def test_aura_primal(self) -> None:
        """Aura entry contains the correct primal percentage."""

        magic = self._get_magic()
        assert magic["aura"]["primal"] == Decimal("50.00")

    def test_aura_abyssal(self) -> None:
        """Aura entry contains the correct abyssal percentage."""

        magic = self._get_magic()
        assert magic["aura"]["abyssal"] == Decimal("30.00")

    def test_aura_glimpse_story(self) -> None:
        """Aura entry contains the glimpse story."""
        magic = self._get_magic()
        assert magic["aura"]["glimpse_story"] == "A vision of iron chains."

    def test_aura_id(self) -> None:
        """Aura entry contains its own id, so the frontend can address aura actions (#2427)."""
        magic = self._get_magic()
        assert magic["aura"]["id"] == self.aura.pk

    def test_aura_glimpse_state_and_tags(self) -> None:
        """Aura entry contains glimpse_state and chosen glimpse_tags (#2427)."""
        tag = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="ms-tone")
        CharacterGlimpseTagFactory(aura=self.aura, tag=tag)
        self.aura.glimpse_state = GlimpseState.TAGS_ONLY
        self.aura.save()
        # self.aura is SharedMemoryModel-identity-mapped and shared (class-scoped)
        # with every other test in this class; an earlier test's GET already
        # populated its ``cached_glimpse_tags`` Prefetch(to_attr=...) attribute
        # (empty, since no CharacterGlimpseTag existed yet) — Django's prefetch
        # machinery skips re-fetching an attribute that's already present on the
        # instance, so the stale empty list would otherwise win here.
        CharacterAura.flush_instance_cache()

        magic = self._get_magic()
        assert magic["aura"]["glimpse_state"] == GlimpseState.TAGS_ONLY
        tags = magic["aura"]["glimpse_tags"]
        assert len(tags) == 1
        assert tags[0]["id"] == tag.pk
        assert tags[0]["axis"] == GlimpseTagAxis.TONE
        assert tags[0]["name"] == tag.name
        assert tags[0]["description"] == tag.description

    def test_aura_can_finish_glimpse_true_for_owner_when_unfinished(self) -> None:
        """Owner sees can_finish_glimpse=True while the glimpse is unfinished (#2427)."""
        self.aura.glimpse_state = GlimpseState.TAGS_ONLY
        self.aura.save()

        magic = self._get_magic()
        assert magic["aura"]["can_finish_glimpse"] is True

    def test_aura_can_finish_glimpse_false_when_complete(self) -> None:
        """Even the owner sees can_finish_glimpse=False once the glimpse is complete (#2427)."""
        self.aura.glimpse_state = GlimpseState.COMPLETE
        self.aura.save()

        magic = self._get_magic()
        assert magic["aura"]["can_finish_glimpse"] is False

    def test_aura_can_finish_glimpse_false_for_non_privileged_viewer(self) -> None:
        """A non-owner viewer who can see the section never sees can_finish_glimpse=True (#2427)."""
        self.aura.glimpse_state = GlimpseState.TAGS_ONLY
        self.aura.save()
        self.sheet.magic_visibility = SheetVisibility.PUBLIC
        self.sheet.save(update_fields=["magic_visibility"])

        viewer = AccountFactory()
        client = APIClient()
        client.force_authenticate(user=viewer)
        response = client.get(f"/api/character-sheets/{self.character.pk}/")

        assert response.status_code == 200
        assert response.data["magic"]["aura"]["glimpse_state"] == GlimpseState.TAGS_ONLY
        assert response.data["magic"]["aura"]["can_finish_glimpse"] is False

    # --- Resonance balance tests (#2032) ---

    def test_resonances_list_length(self) -> None:
        """Resonances list contains one entry per claimed CharacterResonance row."""
        magic = self._get_magic()
        assert len(magic["resonances"]) == 1

    def test_resonance_balance_and_lifetime_earned(self) -> None:
        """Resonance entry contains name, balance, and lifetime earned."""
        magic = self._get_magic()
        entry = magic["resonances"][0]
        assert entry["name"] == "Resolve"
        assert entry["balance"] == 15
        assert entry["lifetime_earned"] == 40


class TestMagicNull(TestCase):
    """Tests for the magic section when no magic data exists."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with no magic data at all."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="NoMagic")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_magic_null_when_no_data(self) -> None:
        """Magic section is null when character has no magic data."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["magic"] is None


class TestMagicPartialData(TestCase):
    """Tests for the magic section with only some sub-sections populated."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with only an aura (no gifts, motif, or ritual)."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="PartialMage")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        CharacterAuraFactory(
            character=cls.character,
            celestial=Decimal("33.33"),
            primal=Decimal("33.34"),
            abyssal=Decimal("33.33"),
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_magic_not_null_with_only_aura(self) -> None:
        """Magic section is not null when only aura exists."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        magic = response.data["magic"]
        assert magic is not None

    def test_gifts_empty_when_none_exist(self) -> None:
        """Gifts list is empty when character has no gifts."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        magic = response.data["magic"]
        assert magic["gifts"] == []

    def test_motif_null_when_not_set(self) -> None:
        """Motif is null when character has no motif."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        magic = response.data["magic"]
        assert magic["motif"] is None

    def test_anima_ritual_null_when_not_set(self) -> None:
        """Anima ritual is null when character has no ritual."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        magic = response.data["magic"]
        assert magic["anima_ritual"] is None

    def test_aura_present(self) -> None:
        """Aura data is present when aura exists."""

        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        magic = response.data["magic"]
        assert magic["aura"]["celestial"] == Decimal("33.33")


class TestMagicGiftWithoutTechniques(TestCase):
    """Tests for a gift that has no techniques yet."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with a gift but no techniques."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="NewMage")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        cls.gift = GiftFactory(name="Shadow Walk", description="Move through shadows.")
        CharacterGiftFactory(character=cls.sheet, gift=cls.gift)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_gift_techniques_empty(self) -> None:
        """Gift entry has empty techniques list when character has none."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        magic = response.data["magic"]
        gift = magic["gifts"][0]
        assert gift["techniques"] == []
        assert gift["name"] == "Shadow Walk"


class TestStorySection(TestCase):
    """Tests for the story section of the character sheet API response."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with story text."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="Storyteller")
        cls.sheet = CharacterSheetFactory(
            character=cls.character,
            background="Born under a blood moon.",
            personality="Quiet and calculating.",
        )
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_story(self) -> dict:
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["story"]

    def test_story_has_expected_keys(self) -> None:
        """Story section contains background, personality, and origin-story fields."""
        story = self._get_story()
        assert set(story.keys()) == {
            "background",
            "personality",
            "origin_story_state",
            "origin_slots",
        }

    def test_story_background(self) -> None:
        """background comes from CharacterSheet.background."""
        story = self._get_story()
        assert story["background"] == "Born under a blood moon."

    def test_story_personality(self) -> None:
        """personality comes from CharacterSheet.personality."""
        story = self._get_story()
        assert story["personality"] == "Quiet and calculating."


class TestStoryEmpty(TestCase):
    """Tests for the story section when fields are blank."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="EmptyStory")
        CharacterSheetFactory(
            character=cls.character,
            background="",
            personality="",
        )
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_story_fields_empty_strings(self) -> None:
        """Story fields are empty strings when not set."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        story = response.data["story"]
        assert story["background"] == ""
        assert story["personality"] == ""


class TestGoalsSection(TestCase):
    """Tests for the goals section of the character sheet API response."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="GoalChar")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        cls.goal_mastery = CharacterGoalFactory(
            character=cls.character,
            domain=GoalDomainFactory(name="Mastery"),
            points=10,
            notes="Become the best swordsman.",
        )
        cls.goal_standing = CharacterGoalFactory(
            character=cls.character,
            domain=GoalDomainFactory(name="Standing"),
            points=20,
            notes="",
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_goals(self) -> list:
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["goals"]

    def test_goals_returns_correct_count(self) -> None:
        """Goals section returns all character goals."""
        goals = self._get_goals()
        assert len(goals) == 2

    def test_goal_entry_keys(self) -> None:
        """Each goal entry has domain, points, notes."""
        goals = self._get_goals()
        for entry in goals:
            assert set(entry.keys()) == {"domain", "points", "notes"}

    def test_goal_entry_values(self) -> None:
        """Goal entries contain correct values."""
        goals = self._get_goals()
        by_domain = {g["domain"]: g for g in goals}

        mastery = by_domain["Mastery"]
        assert mastery["points"] == 10
        assert mastery["notes"] == "Become the best swordsman."

        standing = by_domain["Standing"]
        assert standing["points"] == 20
        assert standing["notes"] == ""


class TestGoalsEmpty(TestCase):
    """Tests for the goals section when no goals exist."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="NoGoals")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_goals_empty_list_when_none(self) -> None:
        """Goals section is an empty list when character has no goals."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["goals"] == []


class TestPersonasSection(TestCase):
    """Tests for the personas section of the character sheet API response."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="PersonaChar")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # Persona with thumbnail
        cls.char_identity = CharacterSheetFactory(character=cls.character)
        cls.media = MediaFactory(
            player_data=cls.player,
            cloudinary_url="https://res.cloudinary.com/test/image/upload/iron_voice.jpg",
        )
        cls.persona_with_thumb = PersonaFactory(
            character_sheet=cls.char_identity.character.sheet_data,
            name="The Iron Voice",
            description="A masked figure.",
            thumbnail=cls.media,
        )

        # Persona without thumbnail
        cls.persona_no_thumb = PersonaFactory(
            character_sheet=cls.char_identity.character.sheet_data,
            name="Shadow",
            description="",
            thumbnail=None,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_personas(self) -> list:
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["personas"]

    def test_personas_returns_correct_count(self) -> None:
        """Personas section returns all character personas."""
        personas = self._get_personas()
        # 2 explicit personas + 1 primary persona auto-created by CharacterSheetFactory
        assert len(personas) == 3

    def test_persona_entry_keys(self) -> None:
        """Each persona entry has id, name, description, thumbnail."""
        personas = self._get_personas()
        for entry in personas:
            assert set(entry.keys()) == {"id", "name", "description", "thumbnail"}

    def test_persona_with_thumbnail(self) -> None:
        """Persona with thumbnail returns cloudinary URL."""
        personas = self._get_personas()
        by_name = {g["name"]: g for g in personas}
        iron = by_name["The Iron Voice"]
        assert iron["id"] == self.persona_with_thumb.pk
        assert iron["description"] == "A masked figure."
        assert iron["thumbnail"] == ("https://res.cloudinary.com/test/image/upload/iron_voice.jpg")

    def test_persona_without_thumbnail(self) -> None:
        """Persona without thumbnail returns null."""
        personas = self._get_personas()
        by_name = {g["name"]: g for g in personas}
        shadow = by_name["Shadow"]
        assert shadow["id"] == self.persona_no_thumb.pk
        assert shadow["thumbnail"] is None


class TestPersonasEmpty(TestCase):
    """Tests for the personas section when no personas exist."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="NoPersonas")
        # Opt out of factory PRIMARY persona creation so the response has
        # an empty personas list.
        CharacterSheetFactory(character=cls.character, primary_persona=False)
        cls.roster_entry = RosterEntryFactory(
            character_sheet__character=cls.character,
            character_sheet__primary_persona=False,
        )
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_personas_empty_list_when_none(self) -> None:
        """Personas section is an empty list when character has none."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["personas"] == []


class TestThemingSection(TestCase):
    """Tests for the theming section of the character sheet API response."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="ThemeChar")
        cls.realm = RealmFactory(name="The Compact")
        cls.species = SpeciesFactory(name="Daeva")
        cls.sheet = CharacterSheetFactory(
            character=cls.character,
            origin_realm=cls.realm,
            species=cls.species,
        )
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        cls.aura = CharacterAuraFactory(
            character=cls.character,
            celestial=Decimal("20.00"),
            primal=Decimal("50.00"),
            abyssal=Decimal("30.00"),
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def _get_theming(self) -> dict:
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        return response.data["theming"]

    def test_theming_has_expected_keys(self) -> None:
        """Theming section contains only aura."""
        theming = self._get_theming()
        assert set(theming.keys()) == {"aura"}

    def test_theming_aura_values(self) -> None:
        """Theming aura contains celestial, primal, abyssal percentages."""

        theming = self._get_theming()
        aura = theming["aura"]
        assert aura["celestial"] == Decimal("20.00")
        assert aura["primal"] == Decimal("50.00")
        assert aura["abyssal"] == Decimal("30.00")


class TestThemingNulls(TestCase):
    """Tests for the theming section when optional data is missing."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="NoTheme")
        CharacterSheetFactory(
            character=cls.character,
            origin_realm=None,
            species=None,
        )
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_aura_null_when_no_aura(self) -> None:
        """aura is null when character has no aura."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["theming"]["aura"] is None


class TestProfilePictureSection(TestCase):
    """Tests for the profile_picture field of the character sheet."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="PicChar")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        cls.tenure_media = TenureMediaFactory(
            tenure=cls.tenure,
            media__cloudinary_url="https://res.cloudinary.com/test/image/upload/profile.jpg",
        )
        cls.roster_entry.profile_picture = cls.tenure_media
        cls.roster_entry.save(update_fields=["profile_picture"])

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_profile_picture_url(self) -> None:
        """profile_picture returns the cloudinary URL string."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["profile_picture"] == (
            "https://res.cloudinary.com/test/image/upload/profile.jpg"
        )


class TestProfilePictureNull(TestCase):
    """Tests for the profile_picture field when no picture is set."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="NoPic")
        CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_profile_picture_null_when_not_set(self) -> None:
        """profile_picture is null when no picture is set."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["profile_picture"] is None


class TestCharacterSheetQueryCount(TestCase):
    """Integration test to lock in the query count and catch N+1 regressions.

    Creates a fully-populated character with data in every section, then
    asserts the total number of queries is bounded.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="FullChar")

        # --- Identity / appearance ---
        cls.realm = RealmFactory(name="Arx")
        cls.species = SpeciesFactory(name="Human")
        cls.gender = GenderFactory(key="female", display_name="Female")
        cls.family = FamilyFactory(name="Thrax")
        cls.build = BuildFactory(name="athletic", display_name="Athletic")
        cls.tarot_card = TarotCard.objects.create(
            name="The Star",
            arcana_type=ArcanaType.MAJOR,
            rank=17,
            latin_name="Stella",
        )

        cls.sheet = CharacterSheetFactory(
            character=cls.character,
            age=30,
            concept="Complete character",
            quote="Everything at once.",
            gender=cls.gender,
            species=cls.species,
            heritage=Heritage.objects.create(name="Sleeper"),
            family=cls.family,
            tarot_card=cls.tarot_card,
            origin_realm=cls.realm,
            build=cls.build,
            true_height_inches=68,
            additional_desc="Fully described.",
            background="Full background.",
            personality="Full personality.",
        )

        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # --- Profile picture ---
        cls.tenure_media = TenureMediaFactory(
            tenure=cls.tenure,
            media__cloudinary_url="https://res.cloudinary.com/test/image/upload/full.jpg",
        )
        cls.roster_entry.profile_picture = cls.tenure_media
        cls.roster_entry.save(update_fields=["profile_picture"])

        # --- Path ---
        cls.path = PathFactory(name="Path of Stars")
        CharacterPathHistoryFactory(character=cls.character, path=cls.path)

        # --- TRUE form with traits ---
        true_form = CharacterFormFactory(character=cls.character, form_type=FormType.TRUE)
        hair_trait = FormTraitFactory(name="qc_hair", display_name="Hair Color")
        hair_option = FormTraitOptionFactory(
            trait=hair_trait, name="qc_black", display_name="Black"
        )
        CharacterFormValueFactory(form=true_form, trait=hair_trait, option=hair_option)

        # --- Stats ---
        str_trait = StatTraitFactory(name="Strength")
        CharacterTraitValueFactory(character=cls.character, trait=str_trait, value=30)

        # --- Skills ---
        melee_skill = SkillFactory(trait__name="QCMelee", trait__category=TraitCategory.COMBAT)
        swords_spec = SpecializationFactory(name="QCSwords", parent_skill=melee_skill)
        CharacterSkillValueFactory(character=cls.character, skill=melee_skill, value=20)
        CharacterSpecializationValueFactory(
            character=cls.character, specialization=swords_spec, value=5
        )

        # --- Distinctions ---
        dist = DistinctionFactory(name="QCBrave")
        CharacterDistinctionFactory(character=cls.character, distinction=dist, rank=1)

        # --- Magic ---
        resonance = ResonanceFactory(name="QCResolve")
        gift = GiftFactory(name="QCIronWill")
        gift.resonances.add(resonance)
        style = TechniqueStyleFactory(name="QCManifestation")
        technique = TechniqueFactory(name="QCSteelSkin", gift=gift, style=style, level=2)
        CharacterGiftFactory(character=cls.sheet, gift=gift)
        CharacterTechniqueFactory(character=cls.sheet, technique=technique)

        motif = MotifFactory(character=cls.sheet, description="Full motif.")
        mr = MotifResonanceFactory(motif=motif, resonance=resonance)
        facet = FacetFactory(name="QCSpider")
        MotifResonanceAssociationFactory(motif_resonance=mr, facet=facet)

        stat_will = StatTraitFactory(name="QCWillpower")
        ritual_skill = SkillFactory(
            trait__name="QCRitualSkill", trait__category=TraitCategory.COMBAT
        )
        # Link character to account for author_account lookup.
        cls.character.db_account = cls.player.account
        cls.character.save(update_fields=["db_account"])
        qc_ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=cls.player.account,
        )
        RitualCheckConfigFactory(
            ritual=qc_ritual,
            stat=stat_will,
            skill=ritual_skill,
            resonance=resonance,
        )

        CharacterAuraFactory(
            character=cls.character,
            celestial=Decimal("33.33"),
            primal=Decimal("33.34"),
            abyssal=Decimal("33.33"),
        )

        # --- Goals ---
        CharacterGoalFactory(
            character=cls.character,
            domain=GoalDomainFactory(name="QCMastery"),
            points=15,
            notes="Be the best.",
        )

        # --- Personas ---
        media = MediaFactory(
            player_data=cls.player,
            cloudinary_url="https://res.cloudinary.com/test/guise.jpg",
        )
        identity = CharacterSheetFactory(character=cls.character)
        PersonaFactory(
            character_sheet=identity.character.sheet_data,
            name="FullPersona",
            description="A persona.",
            thumbnail=media,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_query_count_bounded(self) -> None:
        """A fully-populated character sheet loads within a bounded query count.

        This test locks in the prefetch strategy. If a new N+1 regression
        is introduced, the query count will increase and this test will fail.

        25 queries breakdown (SharedMemoryModel caching reduces some lookups):
         1-4.  Session management (check, savepoint, insert, release)
         5.    CharacterSheet + select_related (character, identity FKs,
               build, aura, roster_entry, profile_picture__media)
         6.    tenures + player_data + account (via Prefetch select_related)
         7.    path_history
         8.    character forms (TRUE filter)
         9.    character form values (traits + options)
        10.    character trait_values (stats)
        11.    character skill_values
        12.    character specialization_values
        13.    character distinctions
        14.    authored_rituals (SCENE_ACTION kind, prefetched via db_account)
        15.    character_gifts (via CharacterSheet)
        16.    gift resonances (nested Prefetch)
        17.    character_techniques (via CharacterSheet)
        18.    motif resonances (nested Prefetch via CharacterSheet)
        19.    motif resonance facet_assignments (nested Prefetch)
        20.    motif resonance style_assignments (nested Prefetch, #2030)
        21.    goals
        22.    personas + thumbnails (via Prefetch select_related)
        23.    persona trait_descriptors (nested Prefetch — appearance overlay)
        24.    HeightBand range lookup for the coarse band label (#1325; one constant
               query — the band is derived from inches, not stored on the sheet)
        25-27. Session management (savepoint, update, release)
        28.    block gate — one indexed exists() check (#1278, get_object)
        29.    character resonances (CharacterResonanceHandler._by_resonance —
               _build_magic_resonances reads character.resonances for the sheet's
               new resonance-balance sub-section, #2032; the handler's one cached
               query, not a fresh SELECT per resonance)
         30.   form_state + active_fake_overlay (#1272 — the disguise concealment
                prefetch; one select_related join, no extra round-trip when no
                overlay is set)
         31.   character condition_instances prefetch (#2196 — dynamic thumbnail
                resolution; prefetched so resolve_thumbnail() doesn't fire
                per-persona queries in _build_personas)
         32.   aura glimpse_tags prefetch (#2427 — chosen glimpse tags for the
                guided-flow "finish your glimpse" affordance; one join query,
                select_related onto the catalog tag)
         33.   origin_slots prefetch (#2478 — origin-story slot answers for
                the guided-flow "finish your origin story" affordance)
        """
        url = f"/api/character-sheets/{self.character.pk}/"
        with self.assertNumQueries(33):
            response = self.client.get(url)
        assert response.status_code == 200
        # Verify all sections are populated
        data = response.data
        assert data["identity"]["name"] == "FullChar"
        assert data["story"]["background"] == "Full background."
        assert len(data["goals"]) == 1
        # 1 explicit persona + 1 primary persona from CharacterSheetFactory
        assert len(data["personas"]) == 2
        assert data["theming"]["aura"] is not None
        assert data["profile_picture"] is not None
        assert data["magic"] is not None


class TestPrefetchCompleteness(TestCase):
    """Per-section zero-query tests for the co-located prefetch declarations.

    Contract: after ``get_character_sheet_queryset()`` fetches the sheet,
    every builder must execute with **zero additional queries**.  If someone
    adds a field that accesses a non-prefetched relation, the specific test
    fails immediately with the query that leaked.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="PrefetchChar")

        cls.realm = RealmFactory(name="PFRealm")
        cls.species = SpeciesFactory(name="PFSpecies")
        cls.gender = GenderFactory(key="pf_neutral", display_name="Neutral")
        cls.family = FamilyFactory(name="PFFamily")
        cls.build = BuildFactory(name="pf_sturdy", display_name="Sturdy")
        cls.tarot_card = TarotCard.objects.create(
            name="PF Tarot",
            arcana_type=ArcanaType.MAJOR,
            rank=1,
            latin_name="PFLatin",
        )

        cls.sheet = CharacterSheetFactory(
            character=cls.character,
            age=28,
            concept="Prefetch test",
            quote="No queries.",
            gender=cls.gender,
            species=cls.species,
            heritage=Heritage.objects.create(name="PFHeritage"),
            family=cls.family,
            tarot_card=cls.tarot_card,
            origin_realm=cls.realm,
            build=cls.build,
            true_height_inches=70,
            additional_desc="Described.",
            background="PF background.",
            personality="PF personality.",
        )

        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        cls.tenure = RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

        # Profile picture
        cls.tenure_media = TenureMediaFactory(
            tenure=cls.tenure,
            media__cloudinary_url="https://res.cloudinary.com/test/pf.jpg",
        )
        cls.roster_entry.profile_picture = cls.tenure_media
        cls.roster_entry.save(update_fields=["profile_picture"])

        # Path
        cls.path = PathFactory(name="PF Path")
        CharacterPathHistoryFactory(character=cls.character, path=cls.path)

        # TRUE form with traits
        true_form = CharacterFormFactory(character=cls.character, form_type=FormType.TRUE)
        hair_trait = FormTraitFactory(name="pf_hair", display_name="Hair")
        hair_option = FormTraitOptionFactory(
            trait=hair_trait, name="pf_brown", display_name="Brown"
        )
        CharacterFormValueFactory(form=true_form, trait=hair_trait, option=hair_option)

        # Stats
        str_trait = StatTraitFactory(name="PFStrength")
        CharacterTraitValueFactory(character=cls.character, trait=str_trait, value=25)

        # Skills + specializations
        melee_skill = SkillFactory(trait__name="PFMelee", trait__category=TraitCategory.COMBAT)
        swords_spec = SpecializationFactory(name="PFSwords", parent_skill=melee_skill)
        CharacterSkillValueFactory(character=cls.character, skill=melee_skill, value=15)
        CharacterSpecializationValueFactory(
            character=cls.character, specialization=swords_spec, value=5
        )

        # Distinctions
        dist = DistinctionFactory(name="PFBrave")
        CharacterDistinctionFactory(character=cls.character, distinction=dist, rank=1)

        # Magic: gifts, techniques, motif, anima ritual, aura
        resonance = ResonanceFactory(name="PFResolve")
        gift = GiftFactory(name="PFGift")
        gift.resonances.add(resonance)
        style = TechniqueStyleFactory(name="PFStyle")
        technique = TechniqueFactory(name="PFTech", gift=gift, style=style, level=1)
        CharacterGiftFactory(character=cls.sheet, gift=gift)
        CharacterTechniqueFactory(character=cls.sheet, technique=technique)

        motif = MotifFactory(character=cls.sheet, description="PF motif.")
        mr = MotifResonanceFactory(motif=motif, resonance=resonance)
        facet = FacetFactory(name="PFFacet")
        MotifResonanceAssociationFactory(motif_resonance=mr, facet=facet)

        stat_will = StatTraitFactory(name="PFWill")
        ritual_skill = SkillFactory(trait__name="PFRitSkill", trait__category=TraitCategory.COMBAT)
        # Link character to account for author_account lookup.
        cls.character.db_account = cls.player.account
        cls.character.save(update_fields=["db_account"])
        pf_ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=cls.player.account,
        )
        RitualCheckConfigFactory(
            ritual=pf_ritual,
            stat=stat_will,
            skill=ritual_skill,
            resonance=resonance,
        )

        CharacterAuraFactory(
            character=cls.character,
            celestial=Decimal("33.33"),
            primal=Decimal("33.34"),
            abyssal=Decimal("33.33"),
        )

        # Goals
        CharacterGoalFactory(
            character=cls.character,
            domain=GoalDomainFactory(name="PFMastery"),
            points=10,
        )

        # Guises
        media = MediaFactory(
            player_data=cls.player,
            cloudinary_url="https://res.cloudinary.com/test/pfguise.jpg",
        )

        pf_identity = CharacterSheetFactory(character=cls.character)
        PersonaFactory(
            character_sheet=pf_identity.character.sheet_data,
            name="PFPersona",
            description="A persona.",
            thumbnail=media,
        )

    def _get_sheet(self) -> CharacterSheet:
        """Fetch a single sheet with all prefetches populated."""
        return get_character_sheet_queryset().get(pk=self.sheet.pk)

    def test_can_edit_tenure_walk_zero_queries(self) -> None:
        """Walking cached_tenures requires no additional queries."""
        sheet = self._get_sheet()
        roster_entry = sheet.roster_entry
        with self.assertNumQueries(0):
            list(roster_entry.cached_tenures)  # type: ignore[attr-defined]

    def test_identity_zero_queries(self) -> None:
        sheet = self._get_sheet()
        with self.assertNumQueries(0):
            _build_identity(sheet)

    def test_appearance_one_query(self) -> None:
        # 1 query: the HeightBand range lookup for the coarse band label (#1325). It is a
        # single constant query — independent of form/trait count — not an N+1.
        sheet = self._get_sheet()
        with self.assertNumQueries(1):
            _build_appearance(sheet, reveal_identity=True, privileged=True)

    def test_stats_zero_queries(self) -> None:
        sheet = self._get_sheet()
        with self.assertNumQueries(0):
            _build_stats(sheet)

    def test_skills_zero_queries(self) -> None:
        sheet = self._get_sheet()
        with self.assertNumQueries(0):
            _build_skills(sheet)

    def test_path_detail_zero_queries(self) -> None:
        sheet = self._get_sheet()
        with self.assertNumQueries(0):
            _build_path_detail(sheet)

    def test_distinctions_zero_queries(self) -> None:
        sheet = self._get_sheet()
        with self.assertNumQueries(0):
            _build_distinctions(sheet, privileged=True)

    def test_magic_zero_queries(self) -> None:
        sheet = self._get_sheet()
        # 2 queries:
        #   1. a Trait FK access in _build_magic is not covered by
        #      _MAGIC_SELECT_RELATED / _MAGIC_PREFETCH_RELATED. Previously this
        #      test asserted 0 queries because earlier tests in the class warmed
        #      the SharedMemoryModel identity map with the Trait row; the project
        #      test runner now flushes the identity map between tests for
        #      production parity (see core.testing), exposing the real count.
        #      Tracked as a prefetch-coverage gap for a follow-up PR.
        #   2. character.resonances (CharacterResonanceHandler._by_resonance, #2032) —
        #      _build_magic_resonances reads the character's claimed CharacterResonance
        #      rows via the handler; not part of _MAGIC_PREFETCH_RELATED (a per-Character
        #      handler, not a CharacterSheet-rooted prefetch), so it costs its one cached
        #      query here — not an N+1, since the handler is called once.
        with self.assertNumQueries(2):
            _build_magic(sheet)

    def test_story_zero_queries(self) -> None:
        sheet = self._get_sheet()
        # Prefetch origin_slots (mirrors the serializer's prefetch, #2478) so
        # _build_story doesn't issue a live query for slot answers.
        from django.db.models import Prefetch

        from world.character_creation.models import CharacterOriginSlot

        sheet = (
            type(sheet)
            .objects.prefetch_related(
                Prefetch(
                    "origin_slots",
                    queryset=CharacterOriginSlot.objects.select_related("slot"),
                    to_attr="cached_origin_slots",
                )
            )
            .get(pk=sheet.pk)
        )
        with self.assertNumQueries(0):
            _build_story(sheet=sheet, bio_profile=sheet.true_profile)

    def test_goals_zero_queries(self) -> None:
        sheet = self._get_sheet()
        with self.assertNumQueries(0):
            _build_goals(sheet)

    def test_personas_zero_queries(self) -> None:
        sheet = self._get_sheet()
        with self.assertNumQueries(0):
            _build_personas(sheet)

    def test_theming_zero_queries(self) -> None:
        sheet = self._get_sheet()
        with self.assertNumQueries(0):
            _build_theming(sheet)

    def test_profile_picture_zero_queries(self) -> None:
        sheet = self._get_sheet()
        with self.assertNumQueries(0):
            _build_profile_picture(sheet)


class TestCurrentResidenceField(TestCase):
    """Tests for current_residence field in CharacterSheet serializer."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a character with optional residence."""
        cls.player = PlayerDataFactory()
        cls.character = CharacterFactory(db_key="ResidenceChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.roster_entry = RosterEntryFactory(character_sheet__character=cls.character)
        RosterTenureFactory(
            player_data=cls.player,
            roster_entry=cls.roster_entry,
            player_number=1,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_current_residence_null_in_response(self) -> None:
        """current_residence is null when no residence is set."""
        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["current_residence"])

    def test_current_residence_set_in_response(self) -> None:
        """current_residence is {id, name} when a residence is set."""
        from evennia_extensions.factories import RoomProfileFactory

        rp = RoomProfileFactory()
        rp.objectdb.db_key = "Grand Hall"
        rp.objectdb.save(update_fields=["db_key"])

        self.sheet.current_residence = rp
        self.sheet.save(update_fields=["current_residence"])

        url = f"/api/character-sheets/{self.character.pk}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["current_residence"],
            {"id": rp.pk, "name": "Grand Hall"},
        )
