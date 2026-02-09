"""FactoryBoy factories for attempt system tests."""

import factory
from factory.django import DjangoModelFactory

from world.attempts.models import AttemptCategory, AttemptConsequence, AttemptTemplate


class AttemptCategoryFactory(DjangoModelFactory):
    class Meta:
        model = AttemptCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"AttemptCategory{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class AttemptTemplateFactory(DjangoModelFactory):
    class Meta:
        model = AttemptTemplate
        django_get_or_create = ("name", "category")

    name = factory.Sequence(lambda n: f"AttemptTemplate{n}")
    category = factory.SubFactory(AttemptCategoryFactory)
    check_type = None  # Must be provided by caller
    description = factory.Faker("sentence")
    is_active = True
    display_order = factory.Sequence(lambda n: n)


class AttemptConsequenceFactory(DjangoModelFactory):
    class Meta:
        model = AttemptConsequence

    attempt_template = factory.SubFactory(AttemptTemplateFactory)
    outcome_tier = None  # Must be provided by caller
    label = factory.Sequence(lambda n: f"Consequence {n}")
    mechanical_description = ""
    weight = 1
    character_loss = False
    display_order = factory.Sequence(lambda n: n)
