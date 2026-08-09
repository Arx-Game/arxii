"""FactoryBoy factories for registration models."""

import secrets

from django.utils import timezone
import factory
from factory.django import DjangoModelFactory

from world.registration.constants import DEFAULT_INVITE_DURATION_DAYS
from world.registration.models import AccountInvite, RegistrationConfig

_ACCOUNT_FACTORY = "evennia_extensions.factories.AccountFactory"


class RegistrationConfigFactory(DjangoModelFactory):
    class Meta:
        model = RegistrationConfig
        django_get_or_create = ("pk",)

    pk = 1
    registration_open = False


class AccountInviteFactory(DjangoModelFactory):
    class Meta:
        model = AccountInvite

    email = factory.Sequence(lambda n: f"invitee{n}@example.com")
    token = factory.LazyFunction(lambda: secrets.token_urlsafe(32))
    invited_by = factory.SubFactory(_ACCOUNT_FACTORY, is_staff=True)
    expires_at = factory.LazyFunction(
        lambda: timezone.now() + timezone.timedelta(days=DEFAULT_INVITE_DURATION_DAYS)
    )
