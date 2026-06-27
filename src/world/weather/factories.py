import factory
from factory.django import DjangoModelFactory

from world.areas.factories import AreaFactory
from world.locations.constants import StatKey
from world.weather.models import (
    Climate,
    FeastDay,
    RegionWeatherState,
    WeatherEmit,
    WeatherType,
    WeatherTypeExposure,
)


class ClimateFactory(DjangoModelFactory):
    class Meta:
        model = Climate

    name = factory.Sequence(lambda n: f"climate_{n}")
    temperature = 0
    moisture = 0
    is_active = True


class WeatherTypeFactory(DjangoModelFactory):
    class Meta:
        model = WeatherType

    name = factory.Sequence(lambda n: f"weather_{n}")
    is_automated = True
    selection_weight = 1
    min_temperature = None
    max_temperature = None
    is_active = True


class WeatherTypeExposureFactory(DjangoModelFactory):
    class Meta:
        model = WeatherTypeExposure

    weather_type = factory.SubFactory(WeatherTypeFactory)
    stat_key = StatKey.WET
    value = 10


class WeatherEmitFactory(DjangoModelFactory):
    class Meta:
        model = WeatherEmit

    weather_type = factory.SubFactory(WeatherTypeFactory)
    text = factory.Sequence(lambda n: f"PLACEHOLDER emit {n}")
    weight = 1


class RegionWeatherStateFactory(DjangoModelFactory):
    class Meta:
        model = RegionWeatherState

    area = factory.SubFactory(AreaFactory)
    weather_type = factory.SubFactory(WeatherTypeFactory)


class FeastDayFactory(DjangoModelFactory):
    class Meta:
        model = FeastDay

    name = factory.Sequence(lambda n: f"feast_{n}")
    ic_month = 10
    ic_day = 31
    weather_type = factory.SubFactory(WeatherTypeFactory, is_automated=False)
    is_active = True
