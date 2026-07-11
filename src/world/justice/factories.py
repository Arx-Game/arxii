import factory
import factory.django

from world.areas.factories import AreaFactory
from world.justice.constants import DEFAULT_HEAT_WEIGHT
from world.justice.models import AccusationCrimeClaim, AreaLaw, CrimeKind, PersonaHeat
from world.scenes.factories import PersonaFactory
from world.secrets.factories import SecretFactory
from world.societies.factories import SocietyFactory


class CrimeKindFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CrimeKind
        django_get_or_create = ("slug",)

    slug = factory.Sequence(lambda n: f"crime-{n}")
    name = factory.Sequence(lambda n: f"Crime {n}")
    description = ""


class AreaLawFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AreaLaw

    area = factory.SubFactory(AreaFactory)
    crime_kind = factory.SubFactory(CrimeKindFactory)
    heat_weight = DEFAULT_HEAT_WEIGHT
    exempts = False


class PersonaHeatFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PersonaHeat

    persona = factory.SubFactory(PersonaFactory)
    area = factory.SubFactory(AreaFactory)
    society = factory.SubFactory(SocietyFactory)
    value = 0


class AccusationCrimeClaimFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AccusationCrimeClaim

    secret = factory.SubFactory(SecretFactory)
    crime_kind = factory.SubFactory(CrimeKindFactory)
    real_deed = None
