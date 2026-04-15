"""GM system factories."""

from datetime import timedelta
import secrets

from django.utils import timezone
import factory
from factory import django as factory_django

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMApplicationStatus, GMLevel
from world.gm.models import (
    GMApplication,
    GMProfile,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
)
from world.roster.factories import RosterEntryFactory
from world.scenes.factories import PersonaFactory


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


class GMTableMembershipFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMTableMembership

    table = factory.SubFactory(GMTableFactory)
    persona = factory.SubFactory(PersonaFactory)  # defaults to ESTABLISHED


class GMRosterInviteFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMRosterInvite

    roster_entry = factory.SubFactory(RosterEntryFactory)
    created_by = factory.SubFactory(GMProfileFactory)
    code = factory.LazyFunction(lambda: secrets.token_urlsafe(48))
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=30))
    is_public = False
