"""Consent seed — default SocialConsentCategory rows + ActionTemplate tagging (#1141).

Seeds the four canonical social consent categories (Romantic, Hostile, Manipulative,
General) and tags each social ActionTemplate with its category. Idempotent — all
writes use ``get_or_create`` / ``update_fields``, so re-runs are no-ops and staff
edits to existing rows are preserved.

Category → action mapping:
  Romantic     → Flirt
  Hostile      → Intimidate
  Manipulative → Deceive, Persuade
  General      → Perform, Entrance, Restore to Sense
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.consent.models import SocialConsentCategory

# (key, name, description, display_order)
_CATEGORIES: tuple[tuple[str, str, str, int], ...] = (
    (
        "romantic",
        "Romantic",
        "Flirtatious, romantic, or intimacy-adjacent social actions.",
        10,
    ),
    (
        "hostile",
        "Hostile",
        "Threatening, coercive, or aggressive social actions.",
        20,
    ),
    (
        "manipulative",
        "Manipulative",
        "Deceptive, persuasive, or psychologically influencing social actions.",
        30,
    ),
    (
        "general",
        "General",
        "Public-facing social performances and recovery actions with broad audience.",
        40,
    ),
)

# ActionTemplate.name → category key
_TEMPLATE_CATEGORY_MAP: dict[str, str] = {
    "Flirt": "romantic",
    "Intimidate": "hostile",
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
    for key, name, description, display_order in _CATEGORIES:
        cat, _ = SocialConsentCategory.objects.get_or_create(
            key=key,
            defaults={
                "name": name,
                "description": description,
                "display_order": display_order,
            },
        )
        categories[key] = cat

    _tag_action_templates(categories)


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
