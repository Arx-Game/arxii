from django.utils import timezone
import factory
import factory.django as factory_django

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory, GuiseFactory
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    MessageContext,
    MessageMode,
    ScenePrivacyMode,
    SummaryAction,
)
from world.scenes.models import (
    Interaction,
    InteractionAudience,
    InteractionFavorite,
    InteractionTargetPersona,
    Persona,
    PersonaIdentification,
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
    class Meta:
        model = Persona

    guise = factory.SubFactory(GuiseFactory)
    character = factory.LazyAttribute(lambda o: o.guise.character)
    name = factory.LazyAttribute(lambda o: o.guise.name)
    description = factory.Faker("text", max_nb_chars=100)
    thumbnail_url = factory.Faker("image_url")
    participation = None  # Default: no scene participation


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
            # Try to get existing persona for this scene, or create one
            persona = Persona.objects.filter(participation__scene=scene).first()
            if not persona:
                if scene.participations.exists():
                    participation = scene.participations.first()
                    persona = PersonaFactory(participation=participation)
                else:
                    account = AccountFactory()
                    participation = SceneParticipationFactory(
                        scene=scene,
                        account=account,
                    )
                    persona = PersonaFactory(participation=participation)
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
    guise = factory.SubFactory(GuiseFactory)


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


class PersonaIdentificationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = PersonaIdentification

    persona = factory.SubFactory(PersonaFactory, is_fake_name=True)
    identified_by = factory.SubFactory(CharacterSheetFactory)


class SceneSummaryRevisionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SceneSummaryRevision
        exclude = ["account"]

    account = factory.SubFactory(AccountFactory)
    scene = factory.SubFactory(SceneFactory, privacy_mode=ScenePrivacyMode.EPHEMERAL)
    persona = factory.LazyAttribute(
        lambda obj: PersonaFactory(
            participation=SceneParticipationFactory(
                scene=obj.scene,
                account=obj.account,
            ),
        ),
    )
    content = factory.Faker("text", max_nb_chars=300)
    action = SummaryAction.SUBMIT
