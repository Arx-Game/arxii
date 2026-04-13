from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    PersonaType,
    ScenePrivacyMode,
    SummaryAction,
)
from world.scenes.factories import (
    InteractionFactory,
    InteractionFavoriteFactory,
    InteractionReceiverFactory,
    PersonaDiscoveryFactory,
    PersonaFactory,
    SceneFactory,
    SceneParticipationFactory,
    SceneSummaryRevisionFactory,
)
from world.scenes.models import (
    Interaction,
    InteractionFavorite,
    PersonaDiscovery,
    SceneSummaryRevision,
)


class ScenePrivacyModelTests(TestCase):
    """Tests for Scene privacy_mode and summary fields."""

    def test_scene_default_privacy_is_public(self) -> None:
        scene = SceneFactory()
        assert scene.privacy_mode == ScenePrivacyMode.PUBLIC
        assert scene.is_public is True

    def test_ephemeral_scene(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        assert scene.is_ephemeral is True
        assert scene.is_public is False

    def test_private_scene(self) -> None:
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        assert scene.is_public is False
        assert scene.is_ephemeral is False


class InteractionModelTests(TestCase):
    """Tests for the Interaction model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()

    def test_interaction_creation(self) -> None:
        """Test creating an Interaction with all required fields."""
        interaction = Interaction.objects.create(
            persona=self.persona,
            content="Test pose content",
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )
        assert interaction.pk is not None
        assert interaction.mode == InteractionMode.POSE
        assert interaction.visibility == InteractionVisibility.DEFAULT
        assert interaction.scene is None

    def test_interaction_with_scene(self) -> None:
        """Test creating an Interaction linked to a scene."""
        scene = SceneFactory()
        interaction = Interaction.objects.create(
            persona=self.persona,
            scene=scene,
            content="A dramatic pose",
            mode=InteractionMode.POSE,
        )
        assert interaction.scene == scene

    def test_str_method(self) -> None:
        """Test the string representation of an Interaction."""
        interaction = Interaction.objects.create(
            persona=self.persona,
            content="A very long pose that should be truncated in the string representation",
        )
        result = str(interaction)
        assert "..." in result
        assert self.persona.name in result


class PersonaModelTests(TestCase):
    """Tests for the Persona model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.identity = CharacterSheetFactory()

    def test_persona_primary_type(self) -> None:
        """Primary persona exists from CharacterSheetFactory."""
        persona = self.identity.primary_persona
        assert persona.pk is not None
        assert persona.persona_type == PersonaType.PRIMARY

    def test_persona_established_type(self) -> None:
        """Established persona can be created."""
        persona = PersonaFactory(
            character_sheet=self.identity.character.sheet_data,
            persona_type=PersonaType.ESTABLISHED,
        )
        assert persona.pk is not None
        assert persona.is_established_or_primary is True

    def test_persona_temporary_type(self) -> None:
        """Temporary persona is not established_or_primary."""
        persona = PersonaFactory(
            character_sheet=self.identity.character.sheet_data,
            persona_type=PersonaType.TEMPORARY,
        )
        assert persona.pk is not None
        assert persona.is_established_or_primary is False


class PrimaryPersonaPerCharacterSheetConstraintTest(TestCase):
    """Partial unique constraint: one PRIMARY persona per character_sheet."""

    def test_second_primary_persona_on_same_sheet_rejected(self) -> None:
        from world.scenes.models import Persona

        # CharacterSheetFactory creates a PRIMARY persona and ensures a sheet exists
        identity = CharacterSheetFactory()
        sheet = identity.character.sheet_data

        with self.assertRaises(IntegrityError):
            Persona.objects.create(
                character_sheet=sheet,
                name="Second Primary",
                persona_type=PersonaType.PRIMARY,
            )


class PersonaDiscoveryModelTests(TestCase):
    """Tests for the PersonaDiscovery model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.fake_persona = PersonaFactory(is_fake_name=True)
        cls.real_persona = PersonaFactory()
        cls.identifier = CharacterSheetFactory()

    def test_discovery_creation(self) -> None:
        """Test creating a persona discovery."""
        discovery = PersonaDiscovery.objects.create(
            persona=self.fake_persona,
            linked_to=self.real_persona,
            discovered_by=self.identifier,
        )
        assert discovery.pk is not None
        assert discovery.discovered_at is not None

    def test_discovery_unique_constraint(self) -> None:
        """A character can only discover a persona pair once."""
        PersonaDiscovery.objects.create(
            persona=self.fake_persona,
            linked_to=self.real_persona,
            discovered_by=self.identifier,
        )
        with self.assertRaises(IntegrityError):
            PersonaDiscovery.objects.create(
                persona=self.fake_persona,
                linked_to=self.real_persona,
                discovered_by=self.identifier,
            )

    def test_str_method(self) -> None:
        """Test string representation."""
        discovery = PersonaDiscovery.objects.create(
            persona=self.fake_persona,
            linked_to=self.real_persona,
            discovered_by=self.identifier,
        )
        result = str(discovery)
        assert self.fake_persona.name in result
        assert self.real_persona.name in result

    def test_save_normalizes_pair_order(self) -> None:
        """Creating discovery with reversed order auto-normalizes by PK."""
        low_pk = min(self.fake_persona.pk, self.real_persona.pk)
        high_pk = max(self.fake_persona.pk, self.real_persona.pk)
        low_persona = self.fake_persona if self.fake_persona.pk == low_pk else self.real_persona
        high_persona = self.real_persona if self.real_persona.pk == high_pk else self.fake_persona

        # Pass them in reverse order (high PK first)
        discovery = PersonaDiscovery.objects.create(
            persona=high_persona,
            linked_to=low_persona,
            discovered_by=self.identifier,
        )
        # Should be normalized: lower PK in persona
        assert discovery.persona_id == low_pk
        assert discovery.linked_to_id == high_pk

    def test_clean_normalizes_pair_order(self) -> None:
        """clean() also normalizes ordering."""
        low_pk = min(self.fake_persona.pk, self.real_persona.pk)
        high_pk = max(self.fake_persona.pk, self.real_persona.pk)
        low_persona = self.fake_persona if self.fake_persona.pk == low_pk else self.real_persona
        high_persona = self.real_persona if self.real_persona.pk == high_pk else self.fake_persona

        discovery = PersonaDiscovery(
            persona=high_persona,
            linked_to=low_persona,
            discovered_by=self.identifier,
        )
        discovery.clean()
        assert discovery.persona_id == low_pk
        assert discovery.linked_to_id == high_pk


class InteractionFavoriteModelTests(TestCase):
    """Tests for the InteractionFavorite model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()
        cls.interaction = Interaction.objects.create(
            persona=cls.persona,
            content="A memorable pose",
        )
        cls.roster_entry = InteractionFavoriteFactory.build().roster_entry

    def test_favorite_creation(self) -> None:
        """Test creating a favorite."""
        from world.roster.factories import RosterEntryFactory

        re = RosterEntryFactory()
        favorite = InteractionFavorite.objects.create(
            interaction=self.interaction,
            timestamp=self.interaction.timestamp,
            roster_entry=re,
        )
        assert favorite.pk is not None
        assert favorite.created_at is not None

    def test_favorite_unique_constraint(self) -> None:
        """Test that a roster entry can only favorite an interaction once."""
        from world.roster.factories import RosterEntryFactory

        re = RosterEntryFactory()
        InteractionFavorite.objects.create(
            interaction=self.interaction,
            timestamp=self.interaction.timestamp,
            roster_entry=re,
        )
        with self.assertRaises(IntegrityError):
            InteractionFavorite.objects.create(
                interaction=self.interaction,
                timestamp=self.interaction.timestamp,
                roster_entry=re,
            )

    def test_str_method(self) -> None:
        """Test the string representation of a favorite."""
        from world.roster.factories import RosterEntryFactory

        re = RosterEntryFactory()
        favorite = InteractionFavorite.objects.create(
            interaction=self.interaction,
            timestamp=self.interaction.timestamp,
            roster_entry=re,
        )
        result = str(favorite)
        assert "Favorite" in result
        assert str(self.interaction.pk) in result


class SceneSummaryRevisionModelTests(TestCase):
    """Tests for the SceneSummaryRevision model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        cls.participation = SceneParticipationFactory(scene=cls.scene, account=cls.account)
        cls.persona = PersonaFactory()

    def test_create_summary_revision(self) -> None:
        """A persona can submit a summary revision for an ephemeral scene."""
        revision = SceneSummaryRevision.objects.create(
            scene=self.scene,
            persona=self.persona,
            content="A dramatic confrontation in the garden.",
            action=SummaryAction.SUBMIT,
        )
        assert revision.pk is not None
        assert revision.timestamp is not None
        assert self.persona.name in str(revision)
        assert self.scene.name in str(revision)


class FactoryTests(TestCase):
    """Tests that factories produce valid model instances."""

    def test_interaction_factory(self) -> None:
        """InteractionFactory creates a valid Interaction with persona."""
        interaction = InteractionFactory()
        assert interaction.pk is not None
        assert interaction.persona is not None
        assert interaction.persona.character_sheet is not None

    def test_interaction_receiver_factory(self) -> None:
        """InteractionReceiverFactory creates a valid receiver record."""
        receiver = InteractionReceiverFactory()
        assert receiver.pk is not None
        assert receiver.interaction is not None
        assert receiver.persona is not None

    def test_interaction_favorite_factory(self) -> None:
        """InteractionFavoriteFactory creates a valid favorite."""
        favorite = InteractionFavoriteFactory()
        assert favorite.pk is not None
        assert favorite.created_at is not None

    def test_scene_summary_revision_factory(self) -> None:
        """SceneSummaryRevisionFactory creates a valid revision."""
        revision = SceneSummaryRevisionFactory()
        assert revision.pk is not None
        assert revision.timestamp is not None
        assert revision.scene.is_ephemeral is True

    def test_persona_discovery_factory(self) -> None:
        """PersonaDiscoveryFactory creates a valid discovery."""
        discovery = PersonaDiscoveryFactory()
        assert discovery.pk is not None
        assert discovery.persona.is_fake_name is True
        assert discovery.discovered_by is not None


class PersonaDisplayHelpersTest(TestCase):
    """Tests for Persona.display_ic / display_with_history / display_to_staff."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        # CharacterSheetFactory auto-creates a PRIMARY persona (no separate
        # CharacterIdentity model anymore — it was merged into CharacterSheet
        # in the 2026-04 refactor).
        identity = CharacterSheetFactory(character=cls.sheet.character)
        cls.primary_persona = identity.primary_persona
        cls.primary_persona.character_sheet = cls.sheet
        cls.primary_persona.name = "Bob"
        cls.primary_persona.save()

    def test_display_ic_returns_name(self) -> None:
        assert self.primary_persona.display_ic() == "Bob"

    def test_display_with_history_no_tenure_is_name_only(self) -> None:
        # No RosterEntry exists for this sheet yet
        assert self.primary_persona.display_with_history() == "Bob"

    def test_display_to_staff_no_entry_returns_name(self) -> None:
        assert self.primary_persona.display_to_staff() == "Bob"
