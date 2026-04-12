"""GM system factories."""

from django.utils import timezone
import factory
from factory import django as factory_django

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.models import GMProfile


class GMProfileFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMProfile

    account = factory.SubFactory(AccountFactory)
    level = GMLevel.STARTING
    approved_at = factory.LazyFunction(timezone.now)
    approved_by = factory.SubFactory(AccountFactory)
