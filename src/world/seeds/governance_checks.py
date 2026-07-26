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

``checks.checkcategory``/``checktype``/``checktypetrait``, ``skills.skill``, and
``traits.trait`` are content-repo-owned (#2698) — looked up via
``authored_or_sample()`` rather than invented unless ``SEED_SAMPLE_CONTENT`` is
on. ``skills.specialization``/``checks.checktypespecialization`` stay outside
``CONTENT_MODELS`` and keep seeding unconditionally, but no longer wipe and
rewrite the composition on each run (#2698 Part 1 — that reverted authored/
staff-tuned weights on every Big Button press); ``get_or_create`` converges
instead. Weights are PLACEHOLDER (all 1.0). Both skills are flagged into the
skill-list audit per the provisional-skills rule.
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
    """Look up (or sample) the Governance CheckCategory — content-repo-owned (#2698)."""
    from world.checks.models import CheckCategory  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    return authored_or_sample(
        CheckCategory,
        {
            "description": "Checks for running domains, households, and organizations.",
            "display_order": 40,
        },
        name="Governance",
    )


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
    """Look up (or sample) the Scholarship + Leadership Skill rows + backing Traits.

    ``skills.Skill``/``traits.Trait`` are content-repo-owned (#2698). A skill
    whose Trait or Skill row isn't authored is omitted from the returned dict.
    """
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    skills: dict[str, object] = {}
    for order, (name, tooltip, category) in enumerate(_GOVERNANCE_SKILLS):
        trait = authored_or_sample(
            Trait,
            {
                "trait_type": TraitType.SKILL,
                "category": category,
                "is_public": True,
            },
            name=name,
        )
        if trait is None:
            continue
        skill = authored_or_sample(
            Skill,
            {"tooltip": tooltip, "display_order": 20 + order, "is_active": True},
            trait=trait,
        )
        if skill is None:
            continue
        skills[name] = skill
    return skills


def ensure_governance_specializations(skills: dict[str, object]) -> dict[str, object]:
    """Seed Economics + Stewardship under their parent skills.

    ``skills.Specialization`` is not content-repo-owned — stays unconditional.
    Skipped when the parent skill is missing (its ``parent_skill`` FK is
    required).
    """
    from world.skills.models import Specialization  # noqa: PLC0415

    specs: dict[str, object] = {}
    for order, (name, parent_name) in enumerate(_GOVERNANCE_SPECIALIZATIONS):
        parent_skill = skills.get(parent_name)
        if parent_skill is None:
            continue
        spec, _ = Specialization.objects.get_or_create(
            parent_skill=parent_skill,
            name=name,
            defaults={"display_order": order, "is_active": True},
        )
        specs[name] = spec
    return specs


def _ensure_stat_trait(name: str):
    """Look up (or sample) a MENTAL stat Trait — content-repo-owned (#2698)."""
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    return authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.STAT,
            "category": TraitCategory.MENTAL,
            "is_public": True,
        },
        name=name,
    )


def ensure_governance_check_compositions(
    skills: dict[str, object], specs: dict[str, object]
) -> dict[str, object]:
    """Set each governance CheckType's stat + skill + spec composition.

    ``checks.CheckCategory``/``CheckType``/``CheckTypeTrait`` are content-repo-owned
    (#2698) — looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on.
    No longer wipes and rewrites the composition on each run (#2698 Part 1 — that
    reverted authored/staff-tuned weights on every Big Button press);
    ``get_or_create``/``authored_or_sample`` converge instead.
    """
    from world.checks.models import (  # noqa: PLC0415
        CheckType,
        CheckTypeSpecialization,
        CheckTypeTrait,
    )
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    category = _ensure_governance_category()
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    check_types: dict[str, object] = {}
    if category is None:
        return check_types

    for ct_name, (stat_name, skill_name, spec_name) in _GOVERNANCE_CHECK_COMPOSITION.items():
        check_type = authored_or_sample(
            CheckType, {"is_active": True}, name=ct_name, category=category
        )
        if check_type is None:
            continue

        stat_trait = _ensure_stat_trait(stat_name)
        if stat_trait is not None:
            authored_or_sample(
                CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=stat_trait
            )
        skill = skills.get(skill_name)
        if skill is not None:
            authored_or_sample(
                CheckTypeTrait, {"weight": weight}, check_type=check_type, trait=skill.trait
            )
        spec = specs.get(spec_name)
        if spec is not None:
            CheckTypeSpecialization.objects.get_or_create(
                check_type=check_type, specialization=spec, defaults={"weight": weight}
            )
        check_types[ct_name] = check_type
    return check_types


def seed_governance_check_content() -> None:
    """Cluster entry — seed the governance skills, specializations, and checks (#930)."""
    _rename_legacy_organization()
    skills = ensure_governance_skills()
    specs = ensure_governance_specializations(skills)
    ensure_governance_check_compositions(skills, specs)
