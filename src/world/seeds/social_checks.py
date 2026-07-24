"""Social check content seed (#1688 slice 2) — stat + skill + specialization.

Retrofits the auto-scaffolded **stat+stat** social ``CheckType``s to the design's
**stat + skill (+ specialization)** shape (see ``docs/roadmap/design-tenets.md`` — checks
default to stat + skill (+ spec); stat+stat is the rare exception). Mirrors the code-seed
pattern in ``world/magic/seeds_checks.py``.

**Authoritative + idempotent.** Unlike an additive ``get_or_create`` seed, this sets each
managed CheckType's *exact* composition — it clears the type's existing ``CheckTypeTrait`` /
``CheckTypeSpecialization`` rows and rewrites them — so it corrects the earlier placeholder
(stat+stat) seed wherever it ran, and re-running converges. The ``CheckType`` rows themselves
(and any ``ActionTemplate`` pointing at them) are preserved; only the composition changes.

Weights are PLACEHOLDER (all 1.0) per "build the mechanism, defer the magnitudes". Specializations
contribute only when the character owns them (#1688 engine). ``Presence`` and ``Composure`` are
intentionally **left untouched** — Presence is a flagged placeholder for "some other social check"
and Composure's skill is not yet decided (see #1690).
"""

from __future__ import annotations

from decimal import Decimal

# (skill name, tooltip) — the two parent social skills the checks roll through.
_SOCIAL_SKILLS: list[tuple[str, str]] = [
    ("Persuasion", "Bending others through argument, charm, pressure, and intrigue."),
    ("Performance", "Captivating an audience — song, dance, verse, oratory."),
]

# (specialization name, parent skill name)
_SOCIAL_SPECIALIZATIONS: list[tuple[str, str]] = [
    ("Seduction", "Persuasion"),
    ("Manipulation", "Persuasion"),
    ("Intimidation", "Persuasion"),
    ("Gossip", "Persuasion"),
    ("Propaganda", "Persuasion"),
    ("Singing", "Performance"),
    ("Dancing", "Performance"),
    ("Poetry", "Performance"),
    ("Oratory", "Performance"),
]

# CheckType name -> (stat trait, parent skill, fixed specialization | None).
# A None spec means the spec is runtime-chosen (Performance: which art) or unused (Persuasion base).
_SOCIAL_CHECK_COMPOSITION: dict[str, tuple[str, str, str | None]] = {
    "Intimidation": ("presence", "Persuasion", "Intimidation"),
    "Persuasion": ("charm", "Persuasion", None),
    # Apostate 2026-07-03: deception splits by stat — presence = Deceive
    # (fooling people in the moment, incl. under a disguise), charm = Con
    # (talking someone into a curated version of events).
    "Deceive": ("presence", "Persuasion", "Manipulation"),
    "Con": ("charm", "Persuasion", "Manipulation"),
    "Seduction": ("charm", "Persuasion", "Seduction"),
    "Performance": ("presence", "Performance", None),
    "Gossip": ("charm", "Persuasion", "Gossip"),  # #1572 — the gossip plant/seek/suppress check
    # #1824 — the witness-handling bribery approach (pay them off; the attempt
    # itself is a CrimeKind). Bare Persuasion: no existing spec fits a plain
    # transaction — FLAGGED as a possible spec-list hole for the skills audit.
    "Bribery": ("charm", "Persuasion", None),
}


def _ensure_social_category():
    from world.checks.models import CheckCategory  # noqa: PLC0415

    category, _ = CheckCategory.objects.get_or_create(
        name="Social",
        defaults={
            "description": "Checks involving social interaction, persuasion, and presence.",
            "display_order": 10,
        },
    )
    return category


def ensure_social_skills() -> dict[str, object]:
    """Seed the Persuasion + Performance Skill rows (+ their backing SKILL Traits)."""
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    skills: dict[str, object] = {}
    for order, (name, tooltip) in enumerate(_SOCIAL_SKILLS):
        trait, _ = Trait.objects.get_or_create(
            name=name,
            defaults={
                "trait_type": TraitType.SKILL,
                "category": TraitCategory.SOCIAL,
                "is_public": True,
            },
        )
        skill, _ = Skill.objects.get_or_create(
            trait=trait,
            defaults={"tooltip": tooltip, "display_order": order, "is_active": True},
        )
        skills[name] = skill
    return skills


def ensure_social_specializations(skills: dict[str, object]) -> dict[str, object]:
    """Seed the specialization rows under their parent social skills."""
    from world.skills.models import Specialization  # noqa: PLC0415

    specs: dict[str, object] = {}
    for order, (name, parent_name) in enumerate(_SOCIAL_SPECIALIZATIONS):
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
            "category": TraitCategory.SOCIAL,
            "is_public": True,
        },
    )
    return trait


def _rename_legacy_deception() -> None:
    """One-way data rename: the charm-era "Deception" CheckType becomes "Deceive".

    In-place rename (pk stable) so the Deceive social ActionTemplate's FK
    survives; the authoritative composition rewrite below then re-stats it to
    presence, and "Con" arrives as the charm row. Idempotent: no-ops once
    renamed or on fresh databases.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    legacy = CheckType.objects.filter(name="Deception").first()
    if legacy is not None and not CheckType.objects.filter(name="Deceive").exists():
        legacy.name = "Deceive"
        legacy.save(update_fields=["name"])


def ensure_social_check_compositions(
    skills: dict[str, object], specs: dict[str, object]
) -> dict[str, object]:
    """Set each social CheckType's exact stat + skill (+ spec) composition (authoritative)."""
    from world.checks.models import (  # noqa: PLC0415
        CheckType,
        CheckTypeSpecialization,
        CheckTypeTrait,
    )

    category = _ensure_social_category()
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    check_types: dict[str, object] = {}

    for ct_name, (stat_name, skill_name, spec_name) in _SOCIAL_CHECK_COMPOSITION.items():
        check_type, _ = CheckType.objects.get_or_create(
            name=ct_name, category=category, defaults={"is_active": True}
        )
        # Authoritative: wipe the prior (placeholder) composition, then rewrite it.
        CheckTypeTrait.objects.filter(check_type=check_type).delete()
        CheckTypeSpecialization.objects.filter(check_type=check_type).delete()

        CheckTypeTrait.objects.create(
            check_type=check_type, trait=_ensure_stat_trait(stat_name), weight=weight
        )
        CheckTypeTrait.objects.create(
            check_type=check_type, trait=skills[skill_name].trait, weight=weight
        )
        if spec_name is not None:
            CheckTypeSpecialization.objects.create(
                check_type=check_type, specialization=specs[spec_name], weight=weight
            )
        check_types[ct_name] = check_type
    return check_types


def seed_social_check_content() -> None:
    """Cluster entry — seed the social skills, specializations, and check compositions (#1688)."""
    skills = ensure_social_skills()
    specs = ensure_social_specializations(skills)
    _rename_legacy_deception()
    ensure_social_check_compositions(skills, specs)
    ensure_menace_target()


def ensure_menace_target() -> None:
    """Seed the ``menace`` ModifierTarget — allure's fear-facing sibling (#2632).

    Named by ApostateCD 2026-07-23. Clothing/cosmetics/distinctions grant it
    exactly like allure (any recognized ModifierSource; facets ride the
    equipment walk). Scoping it to the Intimidation CheckType
    (``target_check_type`` OneToOne) makes character menace + equipment +
    fashion flow into Intimidation checks through the existing #767/#512
    check-contribution seam — no new code. Idempotent.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.mechanics.models import ModifierCategory, ModifierTarget  # noqa: PLC0415

    category, _ = ModifierCategory.objects.get_or_create(name="roll_modifier")
    intimidation = CheckType.objects.filter(name="Intimidation").first()
    target, created = ModifierTarget.objects.get_or_create(
        name="menace",
        defaults={"category": category, "target_check_type": intimidation},
    )
    if not created and target.target_check_type_id is None and intimidation is not None:
        target.target_check_type = intimidation
        target.save(update_fields=["target_check_type"])
