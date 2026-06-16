"""Factory classes for consent models."""

import factory
from factory.django import DjangoModelFactory

from world.consent.models import (
    ConsentGroup,
    ConsentGroupMember,
    SocialConsentPreference,
    SocialConsentWhitelist,
)


class ConsentGroupFactory(DjangoModelFactory):
    """Factory for creating ConsentGroup instances."""

    class Meta:
        model = ConsentGroup

    owner = factory.SubFactory("world.roster.factories.RosterTenureFactory")
    name = factory.Sequence(lambda n: f"Group {n}")


class ConsentGroupMemberFactory(DjangoModelFactory):
    """Factory for creating ConsentGroupMember instances."""

    class Meta:
        model = ConsentGroupMember

    group = factory.SubFactory(ConsentGroupFactory)
    tenure = factory.SubFactory("world.roster.factories.RosterTenureFactory")


class SocialConsentPreferenceFactory(DjangoModelFactory):
    class Meta:
        model = SocialConsentPreference

    tenure = factory.SubFactory("world.roster.factories.RosterTenureFactory")
    allow_social_actions = True
    require_whitelist = False


class SocialConsentWhitelistFactory(DjangoModelFactory):
    class Meta:
        model = SocialConsentWhitelist

    owner_tenure = factory.SubFactory("world.roster.factories.RosterTenureFactory")
    allowed_tenure = factory.SubFactory("world.roster.factories.RosterTenureFactory")
