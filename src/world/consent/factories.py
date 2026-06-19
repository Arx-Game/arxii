"""Factory classes for consent models."""

import factory
from factory.django import DjangoModelFactory

from world.consent.constants import ConsentMode
from world.consent.models import (
    ConsentGroup,
    ConsentGroupMember,
    SocialConsentCategory,
    SocialConsentCategoryRule,
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


class SocialConsentCategoryFactory(DjangoModelFactory):
    class Meta:
        model = SocialConsentCategory
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda n: f"category-{n}")
    name = factory.Sequence(lambda n: f"Category {n}")
    display_order = factory.Sequence(lambda n: n)


class SocialConsentPreferenceFactory(DjangoModelFactory):
    class Meta:
        model = SocialConsentPreference

    tenure = factory.SubFactory("world.roster.factories.RosterTenureFactory")
    allow_social_actions = True


class SocialConsentCategoryRuleFactory(DjangoModelFactory):
    class Meta:
        model = SocialConsentCategoryRule

    preference = factory.SubFactory(SocialConsentPreferenceFactory)
    category = factory.SubFactory(SocialConsentCategoryFactory)
    mode = ConsentMode.ALLOWLIST


class SocialConsentWhitelistFactory(DjangoModelFactory):
    class Meta:
        model = SocialConsentWhitelist

    owner_tenure = factory.SubFactory("world.roster.factories.RosterTenureFactory")
    allowed_tenure = factory.SubFactory("world.roster.factories.RosterTenureFactory")
    category = factory.SubFactory(SocialConsentCategoryFactory)
