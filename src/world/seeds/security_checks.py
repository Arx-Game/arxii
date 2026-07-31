"""Security check content seed (#2180) — stealth, intrusion, and escape checks.

Seeds two skills (Skulduggery, Athletics) with their specializations and the
security + criminal CheckType compositions. The existing "Stealth" CheckType
(seeded by stealth_checks.py) is reused for SNEAK — this seed ensures its
composition is correct but does not create a duplicate.

Skulduggery was born "Larceny" (#2180) and renamed with its criminal
specializations for the accusation counter-play (#1825);
:func:`rename_larceny_to_skulduggery` converges pre-rename DBs in place so
every FK (specializations, check compositions, character trait values)
survives the rename.

``checks.checkcategory``/``checktype``/``checktypetrait``, ``skills.skill``, and
``traits.trait`` are content-repo-owned (#2698) — looked up via
``authored_or_sample()`` rather than invented unless ``SEED_SAMPLE_CONTENT`` is
on. ``skills.specialization``/``checks.checktypespecialization`` stay outside
``CONTENT_MODELS`` and keep seeding unconditionally via ``get_or_create``, but
no longer wipe and rewrite a composition on each run (#2698 Part 1 — that
reverted authored/staff-tuned weights on every Big Button press);
``get_or_create``/``authored_or_sample`` converge instead. Mirrors
social_checks.py / combat_checks.py. Weights are PLACEHOLDER (1.0) per
convention.
"""

from __future__ import annotations

from decimal import Decimal

_SKULDUGGERY_TOOLTIP = "Surreptitious manipulation — locks, pockets, and mechanisms."

# (skill name, tooltip) — the two physical skills the security checks roll through.
_SECURITY_SKILLS: list[tuple[str, str]] = [
    ("Skulduggery", _SKULDUGGERY_TOOLTIP),
    ("Athletics", "Running, climbing, jumping, and feats of physical force."),
]

# (specialization name, parent skill name) — the criminal five joined in #1825.
_SECURITY_SPECIALIZATIONS: list[tuple[str, str]] = [
    ("Lockpicking", "Skulduggery"),
    ("Pickpocketing", "Skulduggery"),
    ("Streetwise", "Skulduggery"),
    ("Disguise", "Skulduggery"),
    ("Forgery", "Skulduggery"),
    ("Sleight of Hand", "Skulduggery"),
    ("Climbing", "Athletics"),
]

# CheckType name -> (stat trait name, parent skill name, specialization | None, category name).
# Stat categories: wits=MENTAL, strength=PHYSICAL, agility=PHYSICAL, perception=META.
# #2757: "Break and Enter" and "Escape Through Window" merged into "Athletics" —
# the stat_override is passed by resolve_security_check from SecurityCheckKind.
_SECURITY_CHECK_COMPOSITION: dict[str, tuple[str, str, str | None, str]] = {
    "Lockpick": ("wits", "Skulduggery", "Lockpicking", "Physical"),
    "Athletics": ("strength", "Athletics", "Climbing", "Physical"),
    "Guard Detection": ("perception", "Investigation", None, "Exploration"),
    # #1825 accusation counter-play — the evidence pipeline's three checks.
    "Forge Evidence": ("wits", "Skulduggery", "Forgery", "Physical"),
    "Gather Evidence": ("wits", "Skulduggery", None, "Physical"),
    "Scrutinize Evidence": ("perception", "Investigation", None, "Exploration"),
}

# Stat name -> TraitCategory (matches canonical stat seeds).
_STAT_CATEGORIES: dict[str, str] = {
    "wits": "mental",
    "strength": "physical",
    "agility": "physical",
    "perception": "meta",
}

_CATEGORIES: dict[str, tuple[str, str, int]] = {
    "Physical": ("Physical", "Checks of body, movement, and physical craft.", 20),
    "Exploration": ("Exploration", "Checks involving searching and observation.", 30),
}


def _ensure_category(name: str) -> object | None:
    """Look up (or sample) a security/criminal CheckCategory — content-repo-owned (#2698)."""
    from world.checks.models import CheckCategory  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    description, display_order = _CATEGORIES[name][1], _CATEGORIES[name][2]
    return authored_or_sample(
        CheckCategory,
        {"description": description, "display_order": display_order},
        name=name,
    )


def _ensure_skill(name: str, tooltip: str) -> object | None:
    """Look up (or sample) a PHYSICAL-category Skill + backing Trait (#2698)."""
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait = authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.PHYSICAL,
            "is_public": True,
        },
        name=name,
    )
    if trait is None:
        return None
    return authored_or_sample(
        Skill,
        {"tooltip": tooltip, "display_order": 35, "is_active": True},
        trait=trait,
    )


def _ensure_specialization(name: str, parent_skill) -> object | None:
    """Seed a Specialization under a parent skill.

    ``skills.Specialization`` is not content-repo-owned — stays unconditional.
    Skipped when ``parent_skill`` is missing (its FK is required).
    """
    from world.skills.models import Specialization  # noqa: PLC0415

    if parent_skill is None:
        return None
    spec, _ = Specialization.objects.get_or_create(
        parent_skill=parent_skill,
        name=name,
        defaults={"display_order": 0, "is_active": True},
    )
    return spec


def _ensure_stat_trait(name: str) -> object | None:
    """Look up (or sample) a stat Trait — content-repo-owned (#2698)."""
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    return authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.STAT,
            "category": _STAT_CATEGORIES[name],
            "is_public": True,
        },
        name=name,
    )


def rename_larceny_to_skulduggery() -> None:
    """Converge a pre-#1825 DB: rename the Larceny trait to Skulduggery in place.

    An in-place ``update`` preserves the trait's pk, so every FK (specializations,
    check compositions, character trait values) survives. No-op once a Skulduggery
    trait exists (fresh DBs, already-renamed DBs).
    """
    from world.traits.models import Trait  # noqa: PLC0415

    if Trait.objects.filter(name="Skulduggery").exists():
        return
    # Instance-level save, NOT queryset .update(): Trait is a SharedMemoryModel, and a
    # queryset update would leave the identity-mapped instance holding the old name in
    # memory (a later .save() on it would write "Larceny" back over the rename).
    for trait in Trait.objects.filter(name="Larceny"):
        trait.name = "Skulduggery"
        trait.save(update_fields=["name"])


def ensure_skulduggery_skill() -> object:
    """Seed (or converge) the Skulduggery Skill — the shared entry other seeds call."""
    rename_larceny_to_skulduggery()
    return _ensure_skill("Skulduggery", _SKULDUGGERY_TOOLTIP)


def ensure_security_skills() -> dict[str, object]:
    """Seed the Skulduggery + Athletics Skill rows (+ their backing SKILL Traits).

    Also ensures the Investigation skill exists (seeded by investigation_checks.py,
    but we call get_or_create so this seed is self-sufficient in test setups).
    """
    rename_larceny_to_skulduggery()
    skills: dict[str, object] = {}
    for name, tooltip in _SECURITY_SKILLS:
        skills[name] = _ensure_skill(name, tooltip)
    from world.seeds.investigation_checks import ensure_investigation_skill  # noqa: PLC0415

    skills["Investigation"] = ensure_investigation_skill()
    return skills


def ensure_security_specializations(skills: dict[str, object]) -> dict[str, object]:
    """Seed Lockpicking + Climbing under their parent skills."""
    specs: dict[str, object] = {}
    for name, parent_name in _SECURITY_SPECIALIZATIONS:
        specs[name] = _ensure_specialization(name, skills[parent_name])
    return specs


def ensure_security_check_compositions(
    skills: dict[str, object], specs: dict[str, object]
) -> dict[str, object]:
    """Set each security CheckType's stat + skill (+ spec) composition.

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

    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    check_types: dict[str, object] = {}

    for ct_name, (
        stat_name,
        skill_name,
        spec_name,
        category_name,
    ) in _SECURITY_CHECK_COMPOSITION.items():
        category = _ensure_category(category_name)
        if category is None:
            continue
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
        spec = specs.get(spec_name) if spec_name is not None else None
        if spec is not None:
            CheckTypeSpecialization.objects.get_or_create(
                check_type=check_type, specialization=spec, defaults={"weight": weight}
            )
        check_types[ct_name] = check_type
    return check_types


def seed_security_check_content() -> None:
    """Cluster entry — Skulduggery/Athletics skills + security/criminal checks (#2180, #1825)."""
    skills = ensure_security_skills()
    specs = ensure_security_specializations(skills)
    ensure_security_check_compositions(skills, specs)
