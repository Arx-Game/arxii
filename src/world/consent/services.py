"""Service functions for social consent writes."""

from __future__ import annotations

from django.db import IntegrityError, transaction

from world.consent.constants import ConsentMode
from world.consent.models import (
    SocialConsentBlacklist,
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
    if mode not in ConsentMode.values:
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


@transaction.atomic
def add_social_consent_blacklist(
    owner_tenure: RosterTenure,
    blocked_tenure: RosterTenure,
    category: SocialConsentCategory,
) -> SocialConsentBlacklist:
    """Bar *blocked_tenure* from targeting *owner_tenure* in *category* (#1698).

    The "I'd rather not be antagonized by this specific person" surface — consulted only
    when the owner's category rule is ALL_BUT_BLACKLIST. Weaker than a scenes.Block; the
    blocked party is never told.
    """
    try:
        entry, _ = SocialConsentBlacklist.objects.get_or_create(
            owner_tenure=owner_tenure,
            blocked_tenure=blocked_tenure,
            category=category,
        )
        return entry
    except IntegrityError:
        return SocialConsentBlacklist.objects.get(
            owner_tenure=owner_tenure,
            blocked_tenure=blocked_tenure,
            category=category,
        )


def remove_social_consent_blacklist(
    owner_tenure: RosterTenure,
    blocked_tenure: RosterTenure,
    category: SocialConsentCategory,
) -> bool:
    deleted, _ = SocialConsentBlacklist.objects.filter(
        owner_tenure=owner_tenure,
        blocked_tenure=blocked_tenure,
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
    blacklist = SocialConsentBlacklist.objects.filter(
        owner_tenure=tenure,
    ).select_related("blocked_tenure", "category")
    return {
        "preference": preference,
        "rules": list(rules),
        "whitelist": list(whitelist),
        "blacklist": list(blacklist),
    }
