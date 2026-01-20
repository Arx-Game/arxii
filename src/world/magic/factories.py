import factory

from world.magic.models import Affinity, Resonance
from world.magic.types import AffinityType


class AffinityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Affinity
        django_get_or_create = ("affinity_type",)

    affinity_type = AffinityType.PRIMAL
    name = factory.LazyAttribute(lambda o: o.affinity_type.label)
    description = factory.LazyAttribute(lambda o: f"The {o.affinity_type.label} affinity.")
    admin_notes = ""


class ResonanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Resonance
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Resonance {n}")
    slug = factory.Sequence(lambda n: f"resonance-{n}")
    default_affinity = factory.SubFactory(AffinityFactory)
    description = factory.LazyAttribute(lambda o: f"The {o.name} resonance.")
    admin_notes = ""
