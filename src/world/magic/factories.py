import factory

from world.magic.models import Affinity
from world.magic.types import AffinityType


class AffinityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Affinity
        django_get_or_create = ("affinity_type",)

    affinity_type = AffinityType.PRIMAL
    name = factory.LazyAttribute(lambda o: o.affinity_type.label)
    description = factory.LazyAttribute(lambda o: f"The {o.affinity_type.label} affinity.")
    admin_notes = ""
