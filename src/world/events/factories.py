from django.utils import timezone
import factory
from factory import django as factory_django

from world.events.constants import EventStatus, InvitationTargetType
from world.events.models import Event, EventHost, EventInvitation, EventModification
from world.game_clock.constants import TimePhase


class EventFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Event

    name = factory.Sequence(lambda n: f"Test Event {n}")
    description = factory.Faker("sentence")
    location = factory.SubFactory("evennia_extensions.factories.RoomProfileFactory")
    status = EventStatus.SCHEDULED
    is_public = True
    scheduled_real_time = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=1))
    scheduled_ic_time = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=3))
    time_phase = TimePhase.DAY


class EventHostFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = EventHost

    event = factory.SubFactory(EventFactory)
    persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    is_primary = True


class EventInvitationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = EventInvitation

    event = factory.SubFactory(EventFactory)
    target_type = InvitationTargetType.PERSONA
    target_persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    invited_by = factory.SubFactory("world.scenes.factories.PersonaFactory")


class EventModificationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = EventModification

    event = factory.SubFactory(EventFactory)
    room_description_overlay = "The hall has been decorated with silver banners."
