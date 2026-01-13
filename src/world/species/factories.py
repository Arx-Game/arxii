"""
Factory definitions for species system tests.
"""

import factory
import factory.django as factory_django

from world.character_creation.models import SpeciesArea, SpeciesAreaStatBonus
from world.species.models import Language, Species


class LanguageFactory(factory_django.DjangoModelFactory):
    """Factory for creating Language instances."""

    class Meta:
        model = Language
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"TestLanguage{n}")
    description = factory.LazyAttribute(
        lambda obj: f"The {obj.name} language",
    )


class SpeciesFactory(factory_django.DjangoModelFactory):
    """Factory for creating Species instances."""

    class Meta:
        model = Species
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"TestSpecies{n}")
    description = factory.LazyAttribute(
        lambda obj: f"Description of the {obj.name} species",
    )
    parent = None
    sort_order = 0


class SubspeciesFactory(SpeciesFactory):
    """Factory for creating subspecies (Species with a parent)."""

    parent = factory.SubFactory(SpeciesFactory)
    name = factory.Sequence(lambda n: f"TestSubspecies{n}")
    description = factory.LazyAttribute(
        lambda obj: f"Description of the {obj.name} subspecies of {obj.parent.name}",
    )


class SpeciesAreaFactory(factory_django.DjangoModelFactory):
    """Factory for creating SpeciesArea instances."""

    class Meta:
        model = SpeciesArea

    species = factory.SubFactory(SpeciesFactory)
    # starting_area needs to be passed in or use a SubFactory
    # Avoiding circular import by not importing StartingArea here
    trust_required = 0
    is_available = True
    cg_point_cost = 0
    description_override = ""
    sort_order = 0


class SpeciesAreaStatBonusFactory(factory_django.DjangoModelFactory):
    """Factory for creating SpeciesAreaStatBonus instances."""

    class Meta:
        model = SpeciesAreaStatBonus

    species_area = factory.SubFactory(SpeciesAreaFactory)
    stat = "strength"
    value = 1
