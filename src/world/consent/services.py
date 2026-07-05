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


def _decide_consent_block(
    rule_mode: str | None,
    *,
    actor_present: bool,
    whitelisted: bool,
    blacklisted: bool,
    is_friend: bool,
) -> bool:
    """Per-category consent decision, given a pref exists with the master switch on.

    Shared by the public :func:`consent_blocks_targeting` and the batched
    ``actions.player_interface._consent_excluded_persona_ids`` so the mode logic lives
    in one place (#1909 — moved here from ``actions/player_interface.py``). Returns
    ``True`` when the actor is *blocked* from targeting the owner in this category.

    - ``None`` / ``EVERYONE`` → never blocked (default allow).
    - ``ALL_BUT_BLACKLIST`` → blocked only when the actor is on the blacklist; an unknown
      actor (general-visibility probe) is allowed.
    - ``FRIENDS_WHITELIST`` → allowed only for an OOC friend or a whitelisted actor;
      everyone else — including an unknown actor — is blocked.
    - ``ALLOWLIST`` → allowed only for a whitelisted actor; everyone else blocked.
    """
    if rule_mode is None or rule_mode == ConsentMode.EVERYONE:
        return False
    if rule_mode == ConsentMode.ALL_BUT_BLACKLIST:
        return actor_present and blacklisted
    if rule_mode == ConsentMode.FRIENDS_WHITELIST:
        return not (actor_present and (is_friend or whitelisted))
    # ALLOWLIST — strict default-deny; friendship alone is not enough.
    return not (actor_present and whitelisted)


def _decide_default(category: SocialConsentCategory | None, actor_tenure: object | None) -> bool:
    """Fallback decision when no preference row exists for the owner tenure (#1909).

    Treated as "no per-category rule" — falls through to the category's ``default_mode``.
    ``category=None`` (uncategorized) keeps the legacy default-allow (master switch only).
    """
    if category is None:
        return False
    return _decide_consent_block(
        category.default_mode,
        actor_present=actor_tenure is not None,
        whitelisted=False,
        blacklisted=False,
        is_friend=False,
    )


def consent_blocks_targeting(
    *,
    owner_tenure: RosterTenure,
    category: SocialConsentCategory | None,
    actor_tenure: RosterTenure | None,
) -> bool:
    """True if *owner_tenure*'s consent excludes *actor_tenure* for *category* (#1909).

    The single-tenure gate decision — moved here from
    ``actions.player_interface._tenure_blocks_actor`` so later gates (e.g. the steal
    gate) call one public helper instead of reaching into the dispatch layer. Absent
    preference row and absent per-category rule both fall through to the category's
    ``default_mode`` (EVERYONE preserves legacy default-allow; a default-deny category
    like theft blocks by default). The scene-wide picker sweep batches the same
    decision in ``actions.player_interface._consent_excluded_persona_ids``.
    """
    from world.scenes.friend_services import is_friend as _is_friend  # noqa: PLC0415

    try:
        pref = owner_tenure.social_consent_preference
    except SocialConsentPreference.DoesNotExist:
        return _decide_default(category, actor_tenure)

    if not pref.allow_social_actions:
        return True

    if category is None:
        return False  # uncategorized → master switch only

    rule = SocialConsentCategoryRule.objects.filter(preference=pref, category=category).first()
    rule_mode = rule.mode if rule is not None else category.default_mode
    if actor_tenure is None:
        return _decide_consent_block(
            rule_mode,
            actor_present=False,
            whitelisted=False,
            blacklisted=False,
            is_friend=False,
        )

    whitelisted = SocialConsentWhitelist.objects.filter(
        owner_tenure=owner_tenure, allowed_tenure=actor_tenure, category=category
    ).exists()
    blacklisted = SocialConsentBlacklist.objects.filter(
        owner_tenure=owner_tenure, blocked_tenure=actor_tenure, category=category
    ).exists()
    friended = _is_friend(owner_tenure=owner_tenure, friend_tenure=actor_tenure)
    return _decide_consent_block(
        rule_mode,
        actor_present=True,
        whitelisted=whitelisted,
        blacklisted=blacklisted,
        is_friend=friended,
    )


def theft_category() -> SocialConsentCategory:
    """Lazy seeded row for the theft/antagonism gate (#1909) — default-deny."""
    category, _ = SocialConsentCategory.objects.get_or_create(
        key="theft",
        defaults={
            "name": "Theft & Antagonism",
            "description": "Stealing from you and your belongings.",
            "default_mode": ConsentMode.ALLOWLIST,
        },
    )
    return category


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
