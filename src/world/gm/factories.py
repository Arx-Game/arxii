"""GM system factories."""

from django.utils import timezone
import factory
from factory import django as factory_django

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMApplicationStatus, GMLevel
from world.gm.models import GMApplication, GMProfile, GMTable


class GMProfileFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMProfile

    account = factory.SubFactory(AccountFactory)
    level = GMLevel.STARTING
    approved_at = factory.LazyFunction(timezone.now)
    approved_by = factory.SubFactory(AccountFactory)


class GMApplicationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMApplication

    account = factory.SubFactory(AccountFactory)
    application_text = factory.Faker("paragraph", nb_sentences=5)
    status = GMApplicationStatus.PENDING


class GMTableFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMTable

    gm = factory.SubFactory(GMProfileFactory)
    name = factory.Sequence(lambda n: f"Test Table {n}")
