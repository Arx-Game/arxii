from django.utils import timezone
import factory

from world.scenes.constants import MessageContext, MessageMode
from world.scenes.models import (
    Persona,
    Scene,
    SceneMessage,
    SceneMessageSupplementalData,
    SceneParticipation,
)


class SceneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Scene

    name = factory.Sequence(lambda n: f"Test Scene {n}")
    description = factory.Faker("text", max_nb_chars=200)
    is_active = True
    is_public = True
    date_started = factory.LazyFunction(timezone.now)

    @factory.post_generation
    def participants(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for participant in extracted:
                SceneParticipationFactory(scene=self, account=participant)


class SceneParticipationFactory(factory.django.DjangoModelFactory):
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


class PersonaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Persona

    # Don't auto-create scene - let test provide it
    # scene = factory.SubFactory(SceneFactory)
    name = factory.Faker("name")
    description = factory.Faker("text", max_nb_chars=100)
    thumbnail_url = factory.Faker("image_url")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Ensure we have an account - either provided or use scene's first participant
        if "account" not in kwargs:
            scene = kwargs.get("scene")
            if scene and scene.participants.exists():
                kwargs["account"] = scene.participants.first()
        return super()._create(model_class, *args, **kwargs)


class SceneMessageFactory(factory.django.DjangoModelFactory):
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
        if "persona" not in kwargs and "scene" in kwargs:
            scene = kwargs["scene"]
            # Try to get existing persona for this scene, or create one
            persona = scene.personas.first()
            if not persona:
                if scene.participants.exists():
                    account = scene.participants.first()
                    persona = PersonaFactory(scene=scene, account=account)
                else:
                    # Create a participant for this scene
                    from evennia_extensions.factories import AccountFactory

                    account = AccountFactory()
                    SceneParticipationFactory(scene=scene, account=account)
                    persona = PersonaFactory(scene=scene, account=account)
            kwargs["persona"] = persona
        return super()._create(model_class, *args, **kwargs)


class SceneMessageSupplementalDataFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SceneMessageSupplementalData

    message = factory.SubFactory(SceneMessageFactory)
    data = factory.LazyFunction(lambda: {"formatting": "bold", "color": "red"})
