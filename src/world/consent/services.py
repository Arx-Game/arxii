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


def decide_consent_block(  # noqa: PLR0913 — keyword-only signal flags, one per consent input
    rule_mode: str | None,
    *,
    actor_present: bool,
    whitelisted: bool,
    blacklisted: bool,
    is_friend: bool,
    is_rival: bool,
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
    - ``RIVALS`` → allowed only for a declared *mutual* rival or a whitelisted actor;
      everyone else blocked (#2170).
    - ``ALLOWLIST`` → allowed only for a whitelisted actor; everyone else blocked.
    """
    if rule_mode is None or rule_mode == ConsentMode.EVERYONE:
        return False
    if rule_mode == ConsentMode.ALL_BUT_BLACKLIST:
        return actor_present and blacklisted
    if rule_mode == ConsentMode.FRIENDS_WHITELIST:
        return not (actor_present and (is_friend or whitelisted))
    if rule_mode == ConsentMode.RIVALS:
        # Only a declared *mutual* rival (or a whitelisted actor) may target here (#2170).
        return not (actor_present and (is_rival or whitelisted))
    # ALLOWLIST — strict default-deny; friendship/rivalry alone is not enough.
    return not (actor_present and whitelisted)


# Alias for internal callers pre-dating the public rename (cross-module use is public).
_decide_consent_block = decide_consent_block


def _effective_mode_from_chain(
    pref: SocialConsentPreference | None,
    chain: list[SocialConsentCategory],
) -> str:
    """Resolve the effective ConsentMode for a category's ancestor *chain* (#2170).

    *chain* is ``[leaf, …, root]`` (from :meth:`SocialConsentCategory.ancestor_chain`).
    The first node carrying a player rule for *pref* wins; if *pref* is ``None`` or no node
    on the chain has a rule, the root's ``default_mode`` governs. This is the single
    inheritance rule both the per-tenure gate and the batched picker resolve through.
    """
    if pref is not None:
        rule_modes = {
            rule.category_id: rule.mode
            for rule in SocialConsentCategoryRule.objects.filter(
                preference=pref, category__in=chain
            )
        }
        for node in chain:
            mode = rule_modes.get(node.pk)
            if mode is not None:
                return mode
    return chain[-1].default_mode


def effective_consent_mode(
    pref: SocialConsentPreference | None,
    category: SocialConsentCategory,
) -> str:
    """The ConsentMode governing *(pref, category)* after tree inheritance (#2170).

    Public helper for read surfaces (serializer / telnet summary) that need to show a
    player their *resolved* mode per category, not just their explicit rules. Delegates
    to :func:`_effective_mode_from_chain` over the category's ancestor chain.
    """
    return _effective_mode_from_chain(pref, category.ancestor_chain())


def consent_blocks_targeting(
    *,
    owner_tenure: RosterTenure,
    category: SocialConsentCategory | None,
    actor_tenure: RosterTenure | None,
) -> bool:
    """True if *owner_tenure*'s consent excludes *actor_tenure* for *category* (#1909/#2170).

    The single-tenure gate decision — moved here from
    ``actions.player_interface._tenure_blocks_actor`` so later gates (e.g. the steal
    gate) call one public helper instead of reaching into the dispatch layer.

    Resolution is hierarchical (#2170): the effective mode walks the category's ancestor
    chain (nearest rule wins, else the root's ``default_mode``), so a player who set only
    "All Antagonism" has every category beneath it follow. Whitelist/blacklist entries are
    consulted anywhere on the chain (a whitelist on a parent admits the actor for its
    children too); friendship/rivalry are category-independent. An absent preference row is
    NOT auto-allow — it still resolves to the root default (only the ``allow_social_actions``
    master switch is unique to the preference row). The scene-wide picker sweep batches the
    same decision in ``actions.player_interface._consent_excluded_persona_ids``.
    """
    from world.scenes.friend_services import (  # noqa: PLC0415
        is_friend as _is_friend,
        is_rival as _is_rival,
    )

    # Reverse OneToOne accessor (cached on the tenure instance) rather than a fresh filter,
    # so a warmed caller doesn't pay a query for the common has-a-preference-row path.
    try:
        pref: SocialConsentPreference | None = owner_tenure.social_consent_preference
    except SocialConsentPreference.DoesNotExist:
        pref = None
    if pref is not None and not pref.allow_social_actions:
        return True

    if category is None:
        return False  # uncategorized → master switch only

    chain = category.ancestor_chain()
    rule_mode = _effective_mode_from_chain(pref, chain)
    if actor_tenure is None or rule_mode is None or rule_mode == ConsentMode.EVERYONE:
        # No actor, or default-allow: no relational signal is consulted.
        return _decide_consent_block(
            rule_mode,
            actor_present=actor_tenure is not None,
            whitelisted=False,
            blacklisted=False,
            is_friend=False,
            is_rival=False,
        )

    # Compute ONLY the signals the resolved mode consults. This gate is hot — the steal check
    # runs it per item — so a default-deny mode costs one relational query (the whitelist), not
    # four. Whitelist/blacklist are chain-scoped (a parent entry admits/bars for children).
    whitelisted = blacklisted = friended = rivaled = False
    if rule_mode == ConsentMode.ALL_BUT_BLACKLIST:
        blacklisted = SocialConsentBlacklist.objects.filter(
            owner_tenure=owner_tenure, blocked_tenure=actor_tenure, category__in=chain
        ).exists()
    else:  # FRIENDS_WHITELIST / RIVALS / ALLOWLIST all consult the whitelist first.
        whitelisted = SocialConsentWhitelist.objects.filter(
            owner_tenure=owner_tenure, allowed_tenure=actor_tenure, category__in=chain
        ).exists()
        if not whitelisted and rule_mode == ConsentMode.FRIENDS_WHITELIST:
            friended = _is_friend(owner_tenure=owner_tenure, friend_tenure=actor_tenure)
        elif not whitelisted and rule_mode == ConsentMode.RIVALS:
            rivaled = _is_rival(owner_tenure=owner_tenure, rival_tenure=actor_tenure)
    return _decide_consent_block(
        rule_mode,
        actor_present=True,
        whitelisted=whitelisted,
        blacklisted=blacklisted,
        is_friend=friended,
        is_rival=rivaled,
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


def makeover_category() -> SocialConsentCategory:
    """Lazy seeded row for the makeover/styling gate (#2632) — default-deny.

    Another character applying a cosmetic item to your REAL form (hair dye, a
    restyle, lenses) is a body-autonomy call, so it defaults to allowlist even
    though it's friendly rather than antagonistic — you opt your stylists in.
    """
    category, _ = SocialConsentCategory.objects.get_or_create(
        key="makeover",
        defaults={
            "name": "Makeovers & Styling",
            "description": "Other characters restyling your appearance (dye, cuts, cosmetics).",
            "default_mode": ConsentMode.ALLOWLIST,
        },
    )
    return category


def receiving_stolen_goods_category() -> SocialConsentCategory:
    """Lazy seeded row for the hot-goods receipt gate (#1985) — default-deny.

    Gates whether hot-provenance items (stolen, never recovered) may be given,
    sold, or bequeathed to the owner. Opting in is the OOC acknowledgement that
    reclamation RP may follow; the character stays honestly unaware.
    """
    category, _ = SocialConsentCategory.objects.get_or_create(
        key="receiving-stolen-goods",
        defaults={
            "name": "Receiving Stolen Goods",
            "description": "Whether hot items may be given, sold, or bequeathed to you.",
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
