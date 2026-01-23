"""
Factory definitions for societies system tests.

Provides efficient test data creation using factory_boy to improve
test performance and maintainability.
"""

import factory
import factory.django as factory_django

from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import GuiseFactory
from world.societies.models import (
    LegendEntry,
    LegendSpread,
    Organization,
    OrganizationMembership,
    OrganizationReputation,
    OrganizationType,
    Society,
    SocietyReputation,
)


class SocietyFactory(factory_django.DjangoModelFactory):
    """Factory for creating Society instances."""

    class Meta:
        model = Society
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Society {n}")
    description = factory.Faker("paragraph")
    realm = factory.SubFactory(RealmFactory)

    # Principle values - all default to 0
    mercy = 0
    method = 0
    status = 0
    change = 0
    allegiance = 0
    power = 0


class OrganizationTypeFactory(factory_django.DjangoModelFactory):
    """Factory for creating OrganizationType instances."""

    class Meta:
        model = OrganizationType
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"org_type_{n}")

    # Default rank titles
    rank_1_title = "Leader"
    rank_2_title = "Officer"
    rank_3_title = "Member"
    rank_4_title = "Associate"
    rank_5_title = "Contact"


class OrganizationFactory(factory_django.DjangoModelFactory):
    """Factory for creating Organization instances."""

    class Meta:
        model = Organization
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Organization {n}")
    description = factory.Faker("paragraph")
    society = factory.SubFactory(SocietyFactory)
    org_type = factory.SubFactory(OrganizationTypeFactory)

    # Principle overrides - all null by default (inherit from society)
    mercy_override = None
    method_override = None
    status_override = None
    change_override = None
    allegiance_override = None
    power_override = None

    # Rank title overrides - all blank by default (inherit from org_type)
    rank_1_title_override = ""
    rank_2_title_override = ""
    rank_3_title_override = ""
    rank_4_title_override = ""
    rank_5_title_override = ""


class OrganizationMembershipFactory(factory_django.DjangoModelFactory):
    """
    Factory for creating OrganizationMembership instances.

    Note: The guise must be either is_default=True or is_persistent=True
    to pass model validation. The default GuiseFactory sets is_default=True.
    """

    class Meta:
        model = OrganizationMembership

    organization = factory.SubFactory(OrganizationFactory)
    guise = factory.SubFactory(GuiseFactory)  # GuiseFactory sets is_default=True
    rank = 5  # Default to lowest rank


class SocietyReputationFactory(factory_django.DjangoModelFactory):
    """
    Factory for creating SocietyReputation instances.

    Note: The guise must be either is_default=True or is_persistent=True
    to pass model validation. The default GuiseFactory sets is_default=True.
    """

    class Meta:
        model = SocietyReputation

    guise = factory.SubFactory(GuiseFactory)  # GuiseFactory sets is_default=True
    society = factory.SubFactory(SocietyFactory)
    value = 0  # Default to neutral reputation


class OrganizationReputationFactory(factory_django.DjangoModelFactory):
    """
    Factory for creating OrganizationReputation instances.

    Note: The guise must be either is_default=True or is_persistent=True
    to pass model validation. The default GuiseFactory sets is_default=True.
    """

    class Meta:
        model = OrganizationReputation

    guise = factory.SubFactory(GuiseFactory)  # GuiseFactory sets is_default=True
    organization = factory.SubFactory(OrganizationFactory)
    value = 0  # Default to neutral reputation


class LegendEntryFactory(factory_django.DjangoModelFactory):
    """Factory for creating LegendEntry instances."""

    class Meta:
        model = LegendEntry

    guise = factory.SubFactory(GuiseFactory)
    title = factory.Sequence(lambda n: f"Legendary Deed {n}")
    description = factory.Faker("paragraph")
    base_value = factory.Faker("random_int", min=1, max=100)
    source_note = factory.Faker("sentence")
    location_note = factory.Faker("sentence")


class LegendSpreadFactory(factory_django.DjangoModelFactory):
    """Factory for creating LegendSpread instances."""

    class Meta:
        model = LegendSpread

    legend_entry = factory.SubFactory(LegendEntryFactory)
    spreader_guise = factory.SubFactory(GuiseFactory)
    value_added = factory.Faker("random_int", min=1, max=20)
    description = factory.Faker("paragraph")
    method = factory.Faker("sentence")


# Specialized factories for common test scenarios


class PersistentGuiseFactory(factory_django.DjangoModelFactory):
    """
    Factory for creating a persistent (non-default) Guise.

    Use this when you need a guise that is NOT the default but can still
    hold organization memberships and reputations.
    """

    class Meta:
        model = "character_sheets.Guise"

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    name = factory.Sequence(lambda n: f"Alias {n}")
    colored_name = factory.LazyAttribute(lambda obj: f"|m{obj.name}|n")
    description = ""
    is_default = False
    is_persistent = True


class NobleFamilyOrganizationFactory(OrganizationFactory):
    """Factory for creating noble family organizations with appropriate rank titles."""

    org_type = factory.LazyFunction(
        lambda: OrganizationType.objects.get_or_create(
            name="noble_family",
            defaults={
                "rank_1_title": "Head of House",
                "rank_2_title": "Heir",
                "rank_3_title": "Noble Family Member",
                "rank_4_title": "Distant Relation",
                "rank_5_title": "Ward",
            },
        )[0]
    )


class GuildOrganizationFactory(OrganizationFactory):
    """Factory for creating guild organizations with appropriate rank titles."""

    org_type = factory.LazyFunction(
        lambda: OrganizationType.objects.get_or_create(
            name="guild",
            defaults={
                "rank_1_title": "Guildmaster",
                "rank_2_title": "Master",
                "rank_3_title": "Journeyman",
                "rank_4_title": "Apprentice",
                "rank_5_title": "Initiate",
            },
        )[0]
    )


class SecretSocietyOrganizationFactory(OrganizationFactory):
    """Factory for creating secret society organizations with appropriate rank titles."""

    org_type = factory.LazyFunction(
        lambda: OrganizationType.objects.get_or_create(
            name="secret_society",
            defaults={
                "rank_1_title": "Grand Master",
                "rank_2_title": "Inner Circle",
                "rank_3_title": "Initiate",
                "rank_4_title": "Acolyte",
                "rank_5_title": "Outsider Contact",
            },
        )[0]
    )
