from django.utils import timezone
import factory
import factory.django as factory_django

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterIdentityFactory, CharacterSheetFactory
from world.scenes.action_constants import ActionRequestStatus, DifficultyChoice
from world.scenes.action_models import SceneActionRequest
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    PersonaType,
    ScenePrivacyMode,
    SummaryAction,
)
from world.scenes.models import (
    Interaction,
    InteractionFavorite,
    InteractionReaction,
    InteractionTargetPersona,
    Persona,
    PersonaDiscovery,
    Scene,
    SceneParticipation,
    SceneSummaryRevision,
)
from world.scenes.place_models import InteractionReceiver, Place, PlacePresence


class SceneFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Scene

    name = factory.Sequence(lambda n: f"Test Scene {n}")
    description = factory.Faker("text", max_nb_chars=200)
    is_active = True
    privacy_mode = ScenePrivacyMode.PUBLIC
    date_started = factory.LazyFunction(timezone.now)

    @factory.post_generation
    def participants(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for participant in extracted:
                SceneParticipationFactory(scene=self, account=participant)


class SceneParticipationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SceneParticipation

    # Don't auto-create scene - let test provide it
    # scene = factory.SubFactory(SceneFactory)
    is_gm = False
    is_owner = False
    joined_at = factory.LazyFunction(timezone.now)


class SceneOwnerParticipationFactory(SceneParticipationFactory):
    """Factory for scene owners"""

    is_owner = True


class SceneGMParticipationFactory(SceneParticipationFactory):
    """Factory for scene GMs"""

    is_gm = True


class PersonaFactory(factory_django.DjangoModelFactory):
    """Factory for creating non-primary Persona instances.

    Defaults to ESTABLISHED type. For primary personas, use
    CharacterIdentityFactory and access identity.active_persona.
    """

    class Meta:
        model = Persona

    character_identity = factory.SubFactory(CharacterIdentityFactory)
    character = factory.LazyAttribute(lambda o: o.character_identity.character)
    name = factory.Sequence(lambda n: f"Persona {n}")
    persona_type = PersonaType.ESTABLISHED
    description = factory.Faker("text", max_nb_chars=100)
    thumbnail_url = factory.Faker("image_url")
    is_fake_name = False


class InteractionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Interaction

    persona = factory.SubFactory(PersonaFactory)
    content = factory.Faker("text", max_nb_chars=500)
    mode = InteractionMode.POSE
    visibility = InteractionVisibility.DEFAULT


class InteractionFavoriteFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InteractionFavorite

    interaction = factory.SubFactory(InteractionFactory)
    timestamp = factory.LazyAttribute(lambda obj: obj.interaction.timestamp)
    roster_entry = factory.SubFactory(
        "world.roster.factories.RosterEntryFactory",
    )


class InteractionReactionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InteractionReaction

    interaction = factory.SubFactory(InteractionFactory)
    timestamp = factory.LazyAttribute(lambda o: o.interaction.timestamp)
    account = factory.SubFactory(AccountFactory)
    emoji = "\U0001f44d"


class InteractionTargetPersonaFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InteractionTargetPersona

    interaction = factory.SubFactory(InteractionFactory)
    timestamp = factory.LazyAttribute(lambda obj: obj.interaction.timestamp)
    persona = factory.SubFactory(PersonaFactory)


class PersonaDiscoveryFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = PersonaDiscovery

    persona = factory.SubFactory(PersonaFactory, is_fake_name=True)
    linked_to = factory.SubFactory(PersonaFactory)
    discovered_by = factory.SubFactory(CharacterSheetFactory)


class SceneSummaryRevisionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SceneSummaryRevision
        exclude = ["account"]

    account = factory.SubFactory(AccountFactory)
    scene = factory.SubFactory(SceneFactory, privacy_mode=ScenePrivacyMode.EPHEMERAL)
    persona = factory.LazyAttribute(
        lambda _obj: PersonaFactory(
            character_identity=CharacterIdentityFactory(),
        ),
    )
    content = factory.Faker("text", max_nb_chars=300)
    action = SummaryAction.SUBMIT


class PlaceFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Place

    name = factory.Sequence(lambda n: f"Place {n}")
    description = factory.Faker("text", max_nb_chars=100)
    status = "active"


class PlacePresenceFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = PlacePresence

    place = factory.SubFactory(PlaceFactory)
    persona = factory.SubFactory(PersonaFactory)
    arrived_at = factory.LazyFunction(timezone.now)


class InteractionReceiverFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InteractionReceiver

    interaction = factory.SubFactory(InteractionFactory)
    timestamp = factory.LazyAttribute(lambda obj: obj.interaction.timestamp)
    persona = factory.SubFactory(PersonaFactory)


class SceneActionRequestFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SceneActionRequest

    scene = factory.SubFactory(SceneFactory)
    initiator_persona = factory.SubFactory(PersonaFactory)
    target_persona = factory.SubFactory(PersonaFactory)
    action_key = "intimidate"
    status = ActionRequestStatus.PENDING
    difficulty_choice = DifficultyChoice.NORMAL
