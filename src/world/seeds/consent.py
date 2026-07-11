"""Consent seed — default SocialConsentCategory rows + ActionTemplate tagging (#1141/#2170).

Seeds the canonical social consent categories and the **All Antagonism** root group they
hang under, then tags each social ActionTemplate with its category. Idempotent — writes use
``get_or_create`` / ``update_fields``, so re-runs are no-ops and staff edits to existing rows
are preserved. Parents are applied in a second pass so already-seeded rows are adopted too.

Category tree (#2170 — a leaf with no rule inherits its parent, up to the root's default):
  All Antagonism (root, default FRIENDS_WHITELIST — antagonism is opt-in)
    ├─ Hostile        → Intimidate
    └─ Blackmail      → Blackmail
  Romantic     → Flirt                       (root, EVERYONE)
  Manipulative → Deceive, Persuade           (root, EVERYONE)
  General      → Perform, Entrance, Restore to Sense  (root, EVERYONE)

`theft` (ALLOWLIST, lazily seeded by ``services.theft_category``) is deliberately left as
its own root, NOT under All Antagonism, so the #1909 steal gate keeps its strict opt-in
default rather than loosening to the antagonism root — flagged for review on #2170.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.consent.constants import ConsentMode

if TYPE_CHECKING:
    from world.consent.models import SocialConsentCategory

# (key, name, description, display_order, default_mode)
_CATEGORIES: tuple[tuple[str, str, str, int, str], ...] = (
    (
        "antagonism",
        "All Antagonism",
        # PLACEHOLDER (agent-drafted player-facing copy — Apostate to rewrite, #2170):
        "The umbrella for hostile, coercive play against you. Set this one control and every "
        "antagonism category beneath it follows, unless you override a specific one. Defaults "
        "to Friends + whitelist: only your OOC friends (and anyone you allow) may antagonise "
        "you until you widen it.",
        5,
        # Apostate's ratified opt-in default (#2170): antagonism is opt-in — friends +
        # whitelist only until the player widens it. This root value cascades to every
        # antagonism category that has no rule of its own.
        ConsentMode.FRIENDS_WHITELIST,
    ),
    (
        "romantic",
        "Romantic",
        "Flirtatious, romantic, or intimacy-adjacent social actions.",
        10,
        ConsentMode.EVERYONE,
    ),
    (
        "hostile",
        "Hostile",
        "Threatening, coercive, or aggressive social actions.",
        20,
        # Own default is moot while parented under All Antagonism — it inherits the root
        # (FRIENDS_WHITELIST). Left EVERYONE so an orphaned row (root deleted) is legible.
        ConsentMode.EVERYONE,
    ),
    (
        "blackmail",
        "Blackmail",
        "Coercion by threat of exposing a secret you hold about the target.",
        25,
        # Inherits All Antagonism (FRIENDS_WHITELIST); own value kept as the #1680 default
        # so an orphaned row stays opt-in rather than reverting to EVERYONE.
        ConsentMode.FRIENDS_WHITELIST,
    ),
    (
        "manipulative",
        "Manipulative",
        "Deceptive, persuasive, or psychologically influencing social actions.",
        30,
        ConsentMode.EVERYONE,
    ),
    (
        "general",
        "General",
        "Public-facing social performances and recovery actions with broad audience.",
        40,
        ConsentMode.EVERYONE,
    ),
)

# child key → parent key (#2170). Applied after all rows exist so already-seeded rows are
# adopted too. Only antagonism leaves are parented; romantic/manipulative/general stay roots.
_CATEGORY_PARENTS: dict[str, str] = {
    "hostile": "antagonism",
    "blackmail": "antagonism",
}

# ActionTemplate.name → category key
_TEMPLATE_CATEGORY_MAP: dict[str, str] = {
    "Flirt": "romantic",
    "Intimidate": "hostile",
    "Blackmail": "blackmail",
    "Deceive": "manipulative",
    "Persuade": "manipulative",
    "Perform": "general",
    "Entrance": "general",
    "Restore to Sense": "general",
}


def seed_social_consent_categories() -> None:
    """Seed default SocialConsentCategory rows and tag social ActionTemplates.

    Idempotent — uses ``get_or_create`` on ``key``.  Re-runs add nothing and
    staff edits to ``name`` / ``description`` survive (``key`` is the natural
    key; other fields are ``defaults``).

    ActionTemplate tagging only runs for templates that already exist (created
    by the social seed cluster or tests).  Missing templates are silently
    skipped — this function is safe to call before the social cluster runs.
    """
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415

    categories: dict[str, SocialConsentCategory] = {}
    for key, name, description, display_order, default_mode in _CATEGORIES:
        cat, _ = SocialConsentCategory.objects.get_or_create(
            key=key,
            defaults={
                "name": name,
                "description": description,
                "display_order": display_order,
                "default_mode": default_mode,
            },
        )
        categories[key] = cat

    _apply_category_parents(categories)
    _tag_action_templates(categories)


def _apply_category_parents(categories: dict[str, SocialConsentCategory]) -> None:
    """Point each antagonism leaf at its parent group (#2170), idempotently.

    Runs as a second pass so rows seeded before the tree existed are adopted on re-run.
    Only writes when the parent actually changes (avoids spurious UPDATE statements),
    mirroring ``_tag_action_templates``.
    """
    for child_key, parent_key in _CATEGORY_PARENTS.items():
        child = categories.get(child_key)
        parent = categories.get(parent_key)
        if child is None or parent is None:
            continue
        if child.parent_id != parent.pk:
            child.parent = parent
            child.save(update_fields=["parent"])


def _tag_action_templates(categories: dict[str, SocialConsentCategory]) -> None:
    """Tag existing social ActionTemplates with their consent categories.

    Skips templates that have not yet been seeded (safe to call in any order).
    Does not overwrite a template whose ``consent_category`` is already set
    to the correct value (avoids spurious UPDATE statements).
    """
    from actions.models import ActionTemplate  # noqa: PLC0415

    for template_name, category_key in _TEMPLATE_CATEGORY_MAP.items():
        category = categories.get(category_key)
        if category is None:
            continue
        try:
            template = ActionTemplate.objects.get(name=template_name)
        except ActionTemplate.DoesNotExist:
            continue
        if template.consent_category_id != category.pk:
            template.consent_category = category
            template.save(update_fields=["consent_category"])
