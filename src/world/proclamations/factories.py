"""Factory-boy factories for proclamations tests (#2842)."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from world.proclamations.models import (
    EdictKind,
    Proclamation,
    StanceArchetype,
)


class StanceArchetypeFactory(DjangoModelFactory):
    class Meta:
        model = StanceArchetype

    name = factory.Sequence(lambda n: f"Stance {n}")
    description = "A test stance."
    mercy_delta = 0
    method_delta = 0
    status_delta = 0
    change_delta = 0
    allegiance_delta = 0
    power_delta = 0


class EdictKindFactory(DjangoModelFactory):
    class Meta:
        model = EdictKind

    name = factory.Sequence(lambda n: f"Edict {n}")
    description = "A test edict kind."
    stance = factory.SubFactory(StanceArchetypeFactory)
    income_gross_pct = 0
    weekly_unrest_delta = 0
    weekly_upkeep_coppers = 0


class ProclamationFactory(DjangoModelFactory):
    class Meta:
        model = Proclamation

    issuer = factory.SubFactory("world.scenes.factories.PersonaFactory")
    stance = factory.SubFactory(StanceArchetypeFactory)
    prose = "A test proclamation."
    check_outcome = "SUCCESS"


# DomainEdictFactory omitted — tests create DomainEdict rows directly with an
# explicit domain (Domain requires an Area FK that varies per test), so a
# SubFactory chain would need to invent an Area + Org + Domain, which is
# simpler to do inline in setUpTestData.
