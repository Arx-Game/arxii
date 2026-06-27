import factory
from factory.django import DjangoModelFactory

from world.weather.models import Climate


class ClimateFactory(DjangoModelFactory):
    class Meta:
        model = Climate

    name = factory.Sequence(lambda n: f"climate_{n}")
    temperature = 0
    moisture = 0
    is_active = True
