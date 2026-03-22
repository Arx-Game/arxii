"""FactoryBoy factories for actions app models."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from actions.models import ConsequencePool, ConsequencePoolEntry


class ConsequencePoolFactory(DjangoModelFactory):
    """Factory for ConsequencePool."""

    class Meta:
        model = ConsequencePool

    name = factory.Sequence(lambda n: f"Pool{n}")
    description = ""
    parent = None


class ConsequencePoolEntryFactory(DjangoModelFactory):
    """Factory for ConsequencePoolEntry."""

    class Meta:
        model = ConsequencePoolEntry

    pool = factory.SubFactory(ConsequencePoolFactory)
    consequence = factory.SubFactory("world.checks.factories.ConsequenceFactory")
    weight_override = None
    is_excluded = False
