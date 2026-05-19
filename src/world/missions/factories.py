"""FactoryBoy factories for the Missions system (Phase 1)."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from world.missions.constants import OptionProduces
from world.missions.models import (
    SOURCE_DISTINCTION,
    Affordance,
    AffordanceBinding,
)


class AffordanceFactory(DjangoModelFactory):
    """Factory for the Affordance lookup model."""

    class Meta:
        model = Affordance
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"affordance-{n}")
    description = factory.Faker("sentence")


class AffordanceBindingFactory(DjangoModelFactory):
    """Factory for AffordanceBinding.

    Defaults to a distinction-sourced BRANCH binding. Callers exercising
    other discriminators pass ``source_kind=`` plus the matching typed FK and
    clear ``source_distinction``; callers exercising checks pass
    ``produces=OptionProduces.CHECK`` with a ``check_type``.
    """

    class Meta:
        model = AffordanceBinding

    source_kind = SOURCE_DISTINCTION
    source_distinction = factory.SubFactory("world.distinctions.factories.DistinctionFactory")
    affordance = factory.SubFactory(AffordanceFactory)
    produces = OptionProduces.BRANCH
    check_type = None
    base_risk = 0
    ic_framing = factory.Faker("sentence")
    rider = None
