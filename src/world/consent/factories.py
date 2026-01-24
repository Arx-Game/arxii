"""Factory classes for consent models."""

import factory
from factory.django import DjangoModelFactory

from world.consent.models import ConsentGroup, ConsentGroupMember


class ConsentGroupFactory(DjangoModelFactory):
    """Factory for creating ConsentGroup instances."""

    class Meta:
        model = ConsentGroup

    owner = factory.SubFactory("world.roster.factories.RosterTenureFactory")
    name = factory.Sequence(lambda n: f"Group {n}")


class ConsentGroupMemberFactory(DjangoModelFactory):
    """Factory for creating ConsentGroupMember instances."""

    class Meta:
        model = ConsentGroupMember

    group = factory.SubFactory(ConsentGroupFactory)
    tenure = factory.SubFactory("world.roster.factories.RosterTenureFactory")
