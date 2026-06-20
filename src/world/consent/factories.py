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


# ---------------------------------------------------------------------------
# Default-category helpers
# ---------------------------------------------------------------------------
# These helpers create (or retrieve) the four canonical consent categories.
# They double as seed surfaces for tests and for ``world.seeds.consent``.
# Each uses ``get_or_create`` on the stable ``key`` slug so multiple calls
# within the same test transaction are safe (idempotent).


def make_romantic_category() -> SocialConsentCategory:
    """Return the canonical Romantic SocialConsentCategory (get_or_create)."""
    cat, _ = SocialConsentCategory.objects.get_or_create(
        key="romantic",
        defaults={
            "name": "Romantic",
            "description": "Flirtatious, romantic, or intimacy-adjacent social actions.",
            "display_order": 10,
        },
    )
    return cat


def make_hostile_category() -> SocialConsentCategory:
    """Return the canonical Hostile SocialConsentCategory (get_or_create)."""
    cat, _ = SocialConsentCategory.objects.get_or_create(
        key="hostile",
        defaults={
            "name": "Hostile",
            "description": "Threatening, coercive, or aggressive social actions.",
            "display_order": 20,
        },
    )
    return cat


def make_manipulative_category() -> SocialConsentCategory:
    """Return the canonical Manipulative SocialConsentCategory (get_or_create)."""
    cat, _ = SocialConsentCategory.objects.get_or_create(
        key="manipulative",
        defaults={
            "name": "Manipulative",
            "description": "Deceptive, persuasive, or psychologically influencing social actions.",
            "display_order": 30,
        },
    )
    return cat


def make_general_category() -> SocialConsentCategory:
    """Return the canonical General SocialConsentCategory (get_or_create)."""
    cat, _ = SocialConsentCategory.objects.get_or_create(
        key="general",
        defaults={
            "name": "General",
            "description": (
                "Public-facing social performances and recovery actions with broad audience."
            ),
            "display_order": 40,
        },
    )
    return cat


def make_default_categories() -> dict[str, SocialConsentCategory]:
    """Create (or retrieve) all four canonical consent categories.

    Returns a dict keyed by slug: ``romantic``, ``hostile``, ``manipulative``, ``general``.
    Safe to call multiple times in the same transaction.
    """
    return {
        "romantic": make_romantic_category(),
        "hostile": make_hostile_category(),
        "manipulative": make_manipulative_category(),
        "general": make_general_category(),
    }
