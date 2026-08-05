import factory
from factory.django import DjangoModelFactory

from world.contributors.models import ContentContributor


class ContentContributorFactory(DjangoModelFactory):
    """Factory for ContentContributor rows."""

    class Meta:
        model = ContentContributor
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Contributor {n}")
    notes = ""
