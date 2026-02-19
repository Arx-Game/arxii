import factory
import factory.django

from world.areas.constants import AreaLevel
from world.areas.models import Area


class AreaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Area

    name = factory.Sequence(lambda n: f"area_{n}")
    level = AreaLevel.CITY
    parent = None
    realm = None
    description = ""
