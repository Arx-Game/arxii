from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.roster.factories import RosterEntryFactory
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
    SceneFactory,
    SceneParticipationFactory,
    SceneSummaryRevisionFactory,
)
from world.scenes.models import (
    Interaction,
    InteractionAudience,
    InteractionFavorite,
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
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.location = ObjectDBFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.scene = SceneFactory()
        cls.participation = SceneParticipationFactory(scene=cls.scene, account=cls.account)
        cls.persona = PersonaFactory(participation=cls.participation, character=cls.character)

    def test_interaction_creation(self) -> None:
        """Test creating an Interaction with all required fields."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="Test pose content",
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
            sequence_number=1,
        )
        assert interaction.pk is not None
        assert interaction.mode == InteractionMode.POSE
        assert interaction.visibility == InteractionVisibility.DEFAULT
        assert interaction.scene is None
        assert interaction.persona is None

    def test_interaction_with_scene_and_persona(self) -> None:
        """Test creating an Interaction linked to a scene and persona."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            scene=self.scene,
            persona=self.persona,
            content="A dramatic pose",
            mode=InteractionMode.POSE,
            sequence_number=1,
        )
        assert interaction.scene == self.scene
        assert interaction.persona == self.persona

    def test_auto_sequence_number(self) -> None:
        """Test that sequence_number auto-increments per location."""
        interaction1 = Interaction(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="First pose",
        )
        interaction1.save()
        assert interaction1.sequence_number == 1

        interaction2 = Interaction(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="Second pose",
        )
        interaction2.save()
        assert interaction2.sequence_number == 2

    def test_auto_sequence_per_location(self) -> None:
        """Test that sequence numbers are independent per location."""
        location2 = ObjectDBFactory(db_key="other_location")

        Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="Pose in location 1",
            sequence_number=5,
        )
        interaction_loc2 = Interaction(
            character=self.character,
            roster_entry=self.roster_entry,
            location=location2,
            content="Pose in location 2",
        )
        interaction_loc2.save()
        assert interaction_loc2.sequence_number == 1

    def test_str_method(self) -> None:
        """Test the string representation of an Interaction."""
        interaction = Interaction.objects.create(
            character=self.character,
            roster_entry=self.roster_entry,
            location=self.location,
            content="A very long pose that should be truncated in the string representation",
            sequence_number=1,
        )
        result = str(interaction)
        assert "..." in result
        assert str(self.character) in result


class InteractionAudienceModelTests(TestCase):
    """Tests for the InteractionAudience model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.location = ObjectDBFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.scene = SceneFactory()
        cls.participation = SceneParticipationFactory(scene=cls.scene, account=cls.account)
        cls.persona = PersonaFactory(participation=cls.participation, character=cls.character)
        cls.interaction = Interaction.objects.create(
            character=cls.character,
            roster_entry=cls.roster_entry,
            location=cls.location,
            content="Test interaction",
            sequence_number=1,
        )

    def test_audience_creation(self) -> None:
        """Test creating an audience record."""
        audience = InteractionAudience.objects.create(
            interaction=self.interaction,
            roster_entry=self.roster_entry,
            persona=self.persona,
        )
        assert audience.pk is not None
        assert audience.interaction == self.interaction
        assert audience.persona == self.persona

    def test_audience_without_persona(self) -> None:
        """Test creating an audience record without a persona."""
        audience = InteractionAudience.objects.create(
            interaction=self.interaction,
            roster_entry=self.roster_entry,
        )
        assert audience.persona is None

    def test_audience_unique_constraint(self) -> None:
        """Test that a roster entry can only witness an interaction once."""
        InteractionAudience.objects.create(
            interaction=self.interaction,
            roster_entry=self.roster_entry,
        )
        with self.assertRaises(IntegrityError):
            InteractionAudience.objects.create(
                interaction=self.interaction,
                roster_entry=self.roster_entry,
            )

    def test_str_with_persona(self) -> None:
        """Test string representation with a persona."""
        audience = InteractionAudience.objects.create(
            interaction=self.interaction,
            roster_entry=self.roster_entry,
            persona=self.persona,
        )
        result = str(audience)
        assert self.persona.name in result
        assert "witnessed" in result

    def test_str_without_persona(self) -> None:
        """Test string representation without a persona."""
        audience = InteractionAudience.objects.create(
            interaction=self.interaction,
            roster_entry=self.roster_entry,
        )
        result = str(audience)
        assert "witnessed" in result


class InteractionFavoriteModelTests(TestCase):
    """Tests for the InteractionFavorite model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.location = ObjectDBFactory()
        cls.roster_entry = RosterEntryFactory(character=cls.character)
        cls.interaction = Interaction.objects.create(
            character=cls.character,
            roster_entry=cls.roster_entry,
            location=cls.location,
            content="A memorable pose",
            sequence_number=1,
        )

    def test_favorite_creation(self) -> None:
        """Test creating a favorite."""
        favorite = InteractionFavorite.objects.create(
            interaction=self.interaction,
            roster_entry=self.roster_entry,
        )
        assert favorite.pk is not None
        assert favorite.created_at is not None

    def test_favorite_unique_constraint(self) -> None:
        """Test that a roster entry can only favorite an interaction once."""
        InteractionFavorite.objects.create(
            interaction=self.interaction,
            roster_entry=self.roster_entry,
        )
        with self.assertRaises(IntegrityError):
            InteractionFavorite.objects.create(
                interaction=self.interaction,
                roster_entry=self.roster_entry,
            )

    def test_str_method(self) -> None:
        """Test the string representation of a favorite."""
        favorite = InteractionFavorite.objects.create(
            interaction=self.interaction,
            roster_entry=self.roster_entry,
        )
        result = str(favorite)
        assert "Favorite" in result
        assert str(self.interaction.pk) in result


class SceneSummaryRevisionModelTests(TestCase):
    """Tests for the SceneSummaryRevision model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.EPHEMERAL)
        cls.participation = SceneParticipationFactory(scene=cls.scene, account=cls.account)
        cls.persona = PersonaFactory(participation=cls.participation, character=cls.character)

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
        """InteractionFactory creates a valid Interaction with matching roster_entry."""
        interaction = InteractionFactory()
        assert interaction.pk is not None
        assert interaction.roster_entry.character == interaction.character
        assert interaction.sequence_number >= 1

    def test_interaction_audience_factory(self) -> None:
        """InteractionAudienceFactory creates a valid audience record."""
        audience = InteractionAudienceFactory()
        assert audience.pk is not None
        assert audience.interaction is not None
        assert audience.roster_entry is not None

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
