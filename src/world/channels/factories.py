"""FactoryBoy factories for player channels (#3299)."""

import factory
from factory.django import DjangoModelFactory

from evennia_extensions.factories import AccountFactory
from world.channels.constants import ChannelKind
from world.channels.models import Channel, ChannelBan, ChannelMessage, ChannelSubscription
from world.roster.factories import RosterTenureFactory


class ChannelFactory(DjangoModelFactory):
    """A PUBLIC channel by default; pass ``kind=ORG, organization=...`` for an org one."""

    class Meta:
        model = Channel

    name = factory.Sequence(lambda n: f"Channel {n}")
    kind = ChannelKind.PUBLIC


class ChannelMessageFactory(DjangoModelFactory):
    class Meta:
        model = ChannelMessage

    channel = factory.SubFactory(ChannelFactory)
    author_tenure = factory.SubFactory(RosterTenureFactory)
    body = factory.Faker("sentence")


class ChannelSubscriptionFactory(DjangoModelFactory):
    class Meta:
        model = ChannelSubscription

    account = factory.SubFactory(AccountFactory)
    channel = factory.SubFactory(ChannelFactory)


class ChannelBanFactory(DjangoModelFactory):
    class Meta:
        model = ChannelBan

    channel = factory.SubFactory(ChannelFactory)
    account = factory.SubFactory(AccountFactory)
