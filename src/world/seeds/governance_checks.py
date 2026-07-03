"""Governance check content seed (#930) — the domain-running skills and checks.

Two new skills (Apostate, 2026-07-02): **Scholarship → Economics** (book-learning;
improving domains) and **Leadership → Stewardship** (directing anyone in the
household/org; boosts a dispatched collector). Two check compositions ride them:

- **Tax Collection** — presence + Leadership (+ Stewardship): how well a
  dispatched collection run goes.
- **Household Command** — presence + Leadership (+ Stewardship): the general
  be-obeyed-by-your-household check (in-house scandal containment).
- **Domain Investment** — intellect + Scholarship (+ Economics): improving an
  org's income streams / cracking down on graft.

Mirrors the authoritative wipe-and-rewrite pattern of ``social_checks.py``.
Weights are PLACEHOLDER (all 1.0). Both skills are flagged into the skill-list
audit per the provisional-skills rule.
"""

from __future__ import annotations

from decimal import Decimal

# (skill name, tooltip, TraitCategory) — the two governance parent skills.
_GOVERNANCE_SKILLS: list[tuple[str, str, str]] = [
    (
        "Scholarship",
        "Book learning — history, figures, the patterns behind wealth and rule.",
        "mental",
    ),
    (
        "Leadership",
        "Directing people — households, retainers, crews, and chains of command.",
        "social",
    ),
]

# (specialization name, parent skill name)
_GOVERNANCE_SPECIALIZATIONS: list[tuple[str, str]] = [
    ("Economics", "Scholarship"),
    ("Stewardship", "Leadership"),
]

# CheckType name -> (stat trait, parent skill, specialization).
_GOVERNANCE_CHECK_COMPOSITION: dict[str, tuple[str, str, str]] = {
    "Tax Collection": ("presence", "Leadership", "Stewardship"),
    # The general control-your-household check (Apostate 2026-07-03): be obeyed
    # by household servants — in-house scandal containment, and later the
    # direction bonus atop dispatched functionary agents (#672 seam).
    "Household Command": ("presence", "Leadership", "Stewardship"),
    "Domain Investment": ("intellect", "Scholarship", "Economics"),
}


def _ensure_governance_category():
    from world.checks.models import CheckCategory  # noqa: PLC0415

    category, _ = CheckCategory.objects.get_or_create(
        name="Governance",
        defaults={
            "description": "Checks for running domains, households, and organizations.",
            "display_order": 40,
        },
    )
    return category


def _rename_legacy_organization() -> None:
    """One-way data rename: the "Organization" skill trait becomes "Leadership".

    Apostate 2026-07-03 — Arx 1 continuity. In-place (pk stable) so the
    Stewardship spec + any trait values survive; idempotent on fresh DBs.
    """
    from world.traits.models import Trait  # noqa: PLC0415

    legacy = Trait.objects.filter(name="Organization").first()
    if legacy is not None and not Trait.objects.filter(name="Leadership").exists():
        legacy.name = "Leadership"
        legacy.save(update_fields=["name"])


def ensure_governance_skills() -> dict[str, object]:
    """Seed the Scholarship + Organization Skill rows (+ their backing SKILL Traits)."""
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    skills: dict[str, object] = {}
    for order, (name, tooltip, category) in enumerate(_GOVERNANCE_SKILLS):
        trait, _ = Trait.objects.get_or_create(
            name=name,
            defaults={
                "trait_type": TraitType.SKILL,
                "category": category,
                "is_public": True,
            },
        )
        skill, _ = Skill.objects.get_or_create(
            trait=trait,
            defaults={"tooltip": tooltip, "display_order": 20 + order, "is_active": True},
        )
        skills[name] = skill
    return skills


def ensure_governance_specializations(skills: dict[str, object]) -> dict[str, object]:
    """Seed Economics + Stewardship under their parent skills."""
    from world.skills.models import Specialization  # noqa: PLC0415

    specs: dict[str, object] = {}
    for order, (name, parent_name) in enumerate(_GOVERNANCE_SPECIALIZATIONS):
        spec, _ = Specialization.objects.get_or_create(
            parent_skill=skills[parent_name],
            name=name,
            defaults={"display_order": order, "is_active": True},
        )
        specs[name] = spec
    return specs


def _ensure_stat_trait(name: str):
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait, _ = Trait.objects.get_or_create(
        name=name,
        defaults={
            "trait_type": TraitType.STAT,
            "category": TraitCategory.MENTAL,
            "is_public": True,
        },
    )
    return trait


def ensure_governance_check_compositions(
    skills: dict[str, object], specs: dict[str, object]
) -> dict[str, object]:
    """Set each governance CheckType's stat + skill + spec composition (authoritative)."""
    from world.checks.models import (  # noqa: PLC0415
        CheckType,
        CheckTypeSpecialization,
        CheckTypeTrait,
    )

    category = _ensure_governance_category()
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    check_types: dict[str, object] = {}

    for ct_name, (stat_name, skill_name, spec_name) in _GOVERNANCE_CHECK_COMPOSITION.items():
        check_type, _ = CheckType.objects.get_or_create(
            name=ct_name, category=category, defaults={"is_active": True}
        )
        # Authoritative: wipe the prior composition, then rewrite it.
        CheckTypeTrait.objects.filter(check_type=check_type).delete()
        CheckTypeSpecialization.objects.filter(check_type=check_type).delete()

        CheckTypeTrait.objects.create(
            check_type=check_type, trait=_ensure_stat_trait(stat_name), weight=weight
        )
        CheckTypeTrait.objects.create(
            check_type=check_type, trait=skills[skill_name].trait, weight=weight
        )
        CheckTypeSpecialization.objects.create(
            check_type=check_type, specialization=specs[spec_name], weight=weight
        )
        check_types[ct_name] = check_type
    return check_types


def seed_governance_check_content() -> None:
    """Cluster entry — seed the governance skills, specializations, and checks (#930)."""
    _rename_legacy_organization()
    skills = ensure_governance_skills()
    specs = ensure_governance_specializations(skills)
    ensure_governance_check_compositions(skills, specs)
