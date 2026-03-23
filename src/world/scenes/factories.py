from django.utils import timezone
import factory
import factory.django as factory_django

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterIdentityFactory, CharacterSheetFactory
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    MessageContext,
    MessageMode,
    PersonaType,
    ScenePrivacyMode,
    SummaryAction,
)
from world.scenes.models import (
    Interaction,
    InteractionAudience,
    InteractionFavorite,
    InteractionTargetPersona,
    Persona,
    PersonaDiscovery,
    Scene,
    SceneMessage,
    SceneMessageSupplementalData,
    SceneParticipation,
    SceneSummaryRevision,
)


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


class SceneMessageFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SceneMessage

    # Don't auto-create scene/persona - let test provide them
    # scene = factory.SubFactory(SceneFactory)
    # persona = factory.SubFactory(PersonaFactory)
    content = factory.Faker("text", max_nb_chars=500)
    context = MessageContext.PUBLIC
    mode = MessageMode.POSE
    timestamp = factory.LazyFunction(timezone.now)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Ensure persona belongs to the same scene
        persona_key = "persona"
        scene_key = "scene"
        if persona_key not in kwargs and scene_key in kwargs:
            scene = kwargs[scene_key]
            # Try to get existing persona for this scene
            persona = Persona.objects.filter(
                character__in=scene.participants.values("roster_entries__character"),
            ).first()
            if not persona:
                if scene.participations.exists():
                    identity = CharacterIdentityFactory()
                    persona = identity.active_persona
                else:
                    account = AccountFactory()
                    SceneParticipationFactory(
                        scene=scene,
                        account=account,
                    )
                    identity = CharacterIdentityFactory()
                    persona = identity.active_persona
            kwargs["persona"] = persona
        return super()._create(model_class, *args, **kwargs)


class SceneMessageSupplementalDataFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SceneMessageSupplementalData

    message = factory.SubFactory(SceneMessageFactory)
    data = factory.LazyFunction(lambda: {"formatting": "bold", "color": "red"})


class InteractionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Interaction

    persona = factory.SubFactory(PersonaFactory)
    content = factory.Faker("text", max_nb_chars=500)
    mode = InteractionMode.POSE
    visibility = InteractionVisibility.DEFAULT


class InteractionAudienceFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InteractionAudience

    interaction = factory.SubFactory(InteractionFactory)
    timestamp = factory.LazyAttribute(lambda obj: obj.interaction.timestamp)
    persona = factory.SubFactory(PersonaFactory)


class InteractionFavoriteFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InteractionFavorite

    interaction = factory.SubFactory(InteractionFactory)
    timestamp = factory.LazyAttribute(lambda obj: obj.interaction.timestamp)
    roster_entry = factory.SubFactory(
        "world.roster.factories.RosterEntryFactory",
    )


class InteractionTargetPersonaFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InteractionTargetPersona

    interaction = factory.SubFactory(InteractionFactory)
    timestamp = factory.LazyAttribute(lambda obj: obj.interaction.timestamp)
    persona = factory.SubFactory(PersonaFactory)


class PersonaDiscoveryFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = PersonaDiscovery

    persona_a = factory.SubFactory(PersonaFactory, is_fake_name=True)
    persona_b = factory.SubFactory(PersonaFactory)
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
