"""Service functions for social consent writes."""

from __future__ import annotations

from django.db import IntegrityError, transaction

from world.consent.constants import ConsentMode
from world.consent.models import (
    SocialConsentCategory,
    SocialConsentCategoryRule,
    SocialConsentPreference,
    SocialConsentWhitelist,
)
from world.roster.models import RosterTenure


def set_social_consent_preference(
    tenure: RosterTenure, allow_social_actions: bool
) -> SocialConsentPreference:
    preference, _ = SocialConsentPreference.objects.get_or_create(tenure=tenure)
    preference.allow_social_actions = allow_social_actions
    preference.save(update_fields=["allow_social_actions"])
    return preference


def set_social_consent_category_rule(
    preference: SocialConsentPreference,
    category: SocialConsentCategory,
    mode: str,
) -> SocialConsentCategoryRule:
    if mode not in {ConsentMode.EVERYONE, ConsentMode.ALLOWLIST}:
        msg = f"Invalid consent mode '{mode}'."
        raise ValueError(msg)
    rule, _ = SocialConsentCategoryRule.objects.update_or_create(
        preference=preference,
        category=category,
        defaults={"mode": mode},
    )
    return rule


def remove_social_consent_category_rule(
    preference: SocialConsentPreference,
    category: SocialConsentCategory,
) -> bool:
    deleted, _ = SocialConsentCategoryRule.objects.filter(
        preference=preference, category=category
    ).delete()
    return deleted > 0


@transaction.atomic
def add_social_consent_whitelist(
    owner_tenure: RosterTenure,
    allowed_tenure: RosterTenure,
    category: SocialConsentCategory,
) -> SocialConsentWhitelist:
    try:
        entry, _ = SocialConsentWhitelist.objects.get_or_create(
            owner_tenure=owner_tenure,
            allowed_tenure=allowed_tenure,
            category=category,
        )
        return entry
    except IntegrityError:
        return SocialConsentWhitelist.objects.get(
            owner_tenure=owner_tenure,
            allowed_tenure=allowed_tenure,
            category=category,
        )


def remove_social_consent_whitelist(
    owner_tenure: RosterTenure,
    allowed_tenure: RosterTenure,
    category: SocialConsentCategory,
) -> bool:
    deleted, _ = SocialConsentWhitelist.objects.filter(
        owner_tenure=owner_tenure,
        allowed_tenure=allowed_tenure,
        category=category,
    ).delete()
    return deleted > 0


def get_social_consent_summary(tenure: RosterTenure) -> dict:
    preference = SocialConsentPreference.objects.filter(tenure=tenure).first()
    rules = SocialConsentCategoryRule.objects.filter(
        preference__tenure=tenure,
    ).select_related("category")
    whitelist = SocialConsentWhitelist.objects.filter(
        owner_tenure=tenure,
    ).select_related("allowed_tenure", "category")
    return {
        "preference": preference,
        "rules": list(rules),
        "whitelist": list(whitelist),
    }
