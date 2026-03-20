from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory, GuiseFactory
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    ScenePrivacyMode,
    SummaryAction,
)
from world.scenes.factories import (
    InteractionAudienceFactory,
    InteractionFactory,
    InteractionFavoriteFactory,
    PersonaFactory,
    PersonaIdentificationFactory,
    SceneFactory,
    SceneParticipationFactory,
    SceneSummaryRevisionFactory,
)
from world.scenes.models import (
    Interaction,
    InteractionAudience,
    InteractionFavorite,
    PersonaIdentification,
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
        cls.guise = GuiseFactory()
        cls.persona = PersonaFactory(guise=cls.guise)

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
        cls.guise = GuiseFactory()

    def test_persona_with_nullable_participation(self) -> None:
        """Persona can exist without scene participation (organic grid RP)."""
        persona = PersonaFactory(guise=self.guise, participation=None)
        assert persona.pk is not None
        assert persona.participation is None
        assert persona.scene is None

    def test_persona_with_guise_fk(self) -> None:
        """Persona is backed by a guise."""
        persona = PersonaFactory(guise=self.guise)
        assert persona.guise == self.guise
        assert persona.character == self.guise.character

    def test_persona_with_participation(self) -> None:
        """Persona can be scene-scoped via participation."""
        scene = SceneFactory()
        account = AccountFactory()
        participation = SceneParticipationFactory(scene=scene, account=account)
        persona = PersonaFactory(guise=self.guise, participation=participation)
        assert persona.participation == participation
        assert persona.scene == scene


class PersonaIdentificationModelTests(TestCase):
    """Tests for the PersonaIdentification model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory(is_fake_name=True)
        cls.identifier = CharacterSheetFactory()

    def test_identification_creation(self) -> None:
        """Test creating a persona identification."""
        identification = PersonaIdentification.objects.create(
            persona=self.persona,
            identified_by=self.identifier,
        )
        assert identification.pk is not None
        assert identification.identified_at is not None

    def test_identification_unique_constraint(self) -> None:
        """A character can only identify a persona once."""
        PersonaIdentification.objects.create(
            persona=self.persona,
            identified_by=self.identifier,
        )
        with self.assertRaises(IntegrityError):
            PersonaIdentification.objects.create(
                persona=self.persona,
                identified_by=self.identifier,
            )

    def test_str_method(self) -> None:
        """Test string representation."""
        identification = PersonaIdentification.objects.create(
            persona=self.persona,
            identified_by=self.identifier,
        )
        result = str(identification)
        assert "identified" in result
        assert self.persona.name in result


class InteractionAudienceModelTests(TestCase):
    """Tests for the InteractionAudience model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.guise = GuiseFactory()
        cls.persona = PersonaFactory(guise=cls.guise)
        cls.interaction = Interaction.objects.create(
            persona=cls.persona,
            content="Test interaction",
        )
        cls.audience_guise = GuiseFactory()

    def test_audience_creation(self) -> None:
        """Test creating an audience record."""
        audience_persona = PersonaFactory(guise=self.audience_guise)
        audience = InteractionAudience.objects.create(
            interaction=self.interaction,
            timestamp=self.interaction.timestamp,
            guise=self.audience_guise,
            persona=audience_persona,
        )
        assert audience.pk is not None
        assert audience.interaction == self.interaction
        assert audience.persona == audience_persona

    def test_audience_without_persona(self) -> None:
        """Test creating an audience record without a persona."""
        audience = InteractionAudience.objects.create(
            interaction=self.interaction,
            timestamp=self.interaction.timestamp,
            guise=self.audience_guise,
        )
        assert audience.persona is None

    def test_audience_unique_constraint(self) -> None:
        """Test that a guise can only witness an interaction once."""
        InteractionAudience.objects.create(
            interaction=self.interaction,
            timestamp=self.interaction.timestamp,
            guise=self.audience_guise,
        )
        with self.assertRaises(IntegrityError):
            InteractionAudience.objects.create(
                interaction=self.interaction,
                timestamp=self.interaction.timestamp,
                guise=self.audience_guise,
            )

    def test_str_with_persona(self) -> None:
        """Test string representation with a persona."""
        audience_persona = PersonaFactory(guise=self.audience_guise)
        audience = InteractionAudience.objects.create(
            interaction=self.interaction,
            timestamp=self.interaction.timestamp,
            guise=self.audience_guise,
            persona=audience_persona,
        )
        result = str(audience)
        assert audience_persona.name in result
        assert "witnessed" in result

    def test_str_without_persona(self) -> None:
        """Test string representation without a persona (falls back to guise name)."""
        audience = InteractionAudience.objects.create(
            interaction=self.interaction,
            timestamp=self.interaction.timestamp,
            guise=self.audience_guise,
        )
        result = str(audience)
        assert "witnessed" in result


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
        cls.persona = PersonaFactory(participation=cls.participation)

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
        assert interaction.persona.guise is not None

    def test_interaction_audience_factory(self) -> None:
        """InteractionAudienceFactory creates a valid audience record."""
        audience = InteractionAudienceFactory()
        assert audience.pk is not None
        assert audience.interaction is not None
        assert audience.guise is not None

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

    def test_persona_identification_factory(self) -> None:
        """PersonaIdentificationFactory creates a valid identification."""
        identification = PersonaIdentificationFactory()
        assert identification.pk is not None
        assert identification.persona.is_fake_name is True
        assert identification.identified_by is not None
