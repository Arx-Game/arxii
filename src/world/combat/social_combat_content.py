"""Social-combat content seed (#2015).

Idempotently seeds the content the four social/mental combat verbs need:

* Four ``CheckType`` rows (Rally/Demoralize/Taunt/Parley) with stat + skill
  (+ specialization) compositions, reusing the social skills/specializations
  seeded by ``world.seeds.social_checks`` (``ensure_social_skills`` /
  ``ensure_social_specializations``). Mirrors the authoritative wipe-and-rewrite
  pattern in ``social_checks.ensure_social_check_compositions``.
* An ``Inspired`` ``ConditionTemplate`` (``alters_behavior=False``) — the
  short-lived benefit ``RALLY`` applies to an ally, consumed by the ally's
  next resolved action this round. Mirrors ``conditions/charm_content.py``.
* A ``Charming Word`` ``Technique`` carrying a ``TechniqueAppliedCondition``
  targeting ``ENEMY`` with the already-seeded ``Charmed`` template — so the
  Charm → allegiance flip (``derive_allegiance`` → ``ALLY_OF_CASTER``) is
  player-reachable without requiring the parley verb. Mirrors the technique
  seed pattern in ``combat/defend_content.py``.

``ensure_social_combat_content`` is idempotent (all writes via ``get_or_create``
or the authoritative wipe-and-rewrite) and doubles as integration-test setup
and staff seed data. Safe to call repeatedly.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from world.combat.constants import ActionCategory
from world.conditions.constants import (
    CHARM_CONDITION_NAME,
    DurationType,
)
from world.conditions.models import ConditionCategory, ConditionTemplate
from world.magic.models.gifts import Gift
from world.magic.models.techniques import (
    ConditionTargetKind,
    EffectType,
    Technique,
    TechniqueAppliedCondition,
    TechniqueStyle,
)

if TYPE_CHECKING:
    from world.checks.models import CheckCategory
    from world.traits.models import Trait

# Identity keys
INSPIRED_CONDITION_NAME: str = "Inspired"
CHARM_TECHNIQUE_NAME: str = "Charming Word"

# (check_type_name, stat_trait_name, skill_name, specialization_name | None).
# Reuses the social skills/specializations from seeds/social_checks.py:
# Persuasion + (Intimidation/Seduction) specs, Performance + Oratory spec.
# Taunt rolls wits + Persuasion + Intimidation (a provoking jab).
_SOCIAL_COMBAT_COMPOSITION: tuple[tuple[str, str, str, str | None], ...] = (
    ("Rally", "presence", "Performance", "Oratory"),
    ("Demoralize", "presence", "Persuasion", "Intimidation"),
    ("Taunt", "wits", "Persuasion", "Intimidation"),
    ("Parley", "charm", "Persuasion", "Seduction"),
)


def _ensure_social_category() -> CheckCategory:
    from world.checks.models import CheckCategory  # noqa: PLC0415

    category, _ = CheckCategory.objects.get_or_create(
        name="Social",
        defaults={
            "description": "Checks involving social interaction, persuasion, and presence.",
            "display_order": 10,
        },
    )
    return category


def _ensure_stat_trait(name: str) -> Trait:
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


def _ensure_social_skills_and_specs() -> tuple[dict[str, object], dict[str, object]]:
    """Ensure the Persuasion + Performance skills and their specs exist.

    Delegates to ``seeds.social_checks`` (which is idempotent) so this seed is
    self-contained — it doesn't assume the social-check cluster ran first.
    """
    from world.seeds.social_checks import (  # noqa: PLC0415
        ensure_social_skills,
        ensure_social_specializations,
    )

    skills = ensure_social_skills()
    specs = ensure_social_specializations(skills)
    return skills, specs


def _ensure_social_combat_check_types(
    skills: dict[str, object], specs: dict[str, object]
) -> dict[str, object]:
    """Seed the 4 social-combat CheckTypes with stat + skill (+ spec) composition.

    Authoritative wipe-and-rewrite (mirrors
    ``social_checks.ensure_social_check_compositions``): clears the type's
    existing ``CheckTypeTrait`` / ``CheckTypeSpecialization`` rows and rewrites
    them, so re-running converges. Weights are PLACEHOLDER (1.0).
    """
    from world.checks.models import (  # noqa: PLC0415
        CheckType,
        CheckTypeSpecialization,
        CheckTypeTrait,
    )

    category = _ensure_social_category()
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    check_types: dict[str, object] = {}

    for ct_name, stat_name, skill_name, spec_name in _SOCIAL_COMBAT_COMPOSITION:
        check_type, _ = CheckType.objects.get_or_create(
            name=ct_name, category=category, defaults={"is_active": True}
        )
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


def _ensure_inspired_condition() -> ConditionTemplate:
    """Seed the ``Inspired`` condition category + template (#2015).

    A short-lived benefit RALLY applies to an ally. ``alters_behavior=False`` —
    it is a buff, not a compulsion (ADR-0024: consent gates behavior-alteration,
    not benefit). Duration: 1 round (consumed by the ally's next resolved action).
    """
    category, _ = ConditionCategory.objects.get_or_create(
        name="Inspiration",
        defaults={
            "description": "Rallying and inspirational effects that bolster allies.",
            "is_negative": False,
            "alters_behavior": False,
        },
    )
    template, _ = ConditionTemplate.objects.get_or_create(
        name=INSPIRED_CONDITION_NAME,
        defaults={
            "category": category,
            "description": "Inspired by an ally's rallying words; the next action lands harder.",
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": 1,
            "is_stackable": False,
            "can_be_dispelled": True,
        },
    )
    return template


def _ensure_charm_technique() -> Technique:
    """Seed the ``Charming Word`` technique that applies Charmed to an ENEMY (#2015).

    Makes the Charm → allegiance flip (``derive_allegiance`` → ``ALLY_OF_CASTER``)
    player-reachable without the parley verb. Mirrors the technique seed in
    ``combat/defend_content.py``: direct ORM (``Technique.get_or_create`` +
    ``TechniqueAppliedCondition.get_or_create``), not the budget builder.
    """
    # Ensure the Charmed template exists first (self-contained seed).
    from world.conditions.charm_content import ensure_charm_content  # noqa: PLC0415

    ensure_charm_content()
    charm_gift, _ = Gift.objects.get_or_create(
        name="Charm",
        defaults={"description": "Charm, compulsion, and social influence magic."},
    )
    style, _ = TechniqueStyle.objects.get_or_create(
        name="Subtle",
        defaults={"description": "Magic that manifests without obvious display."},
    )
    effect_type, _ = EffectType.objects.get_or_create(
        name="Compulsion",
        defaults={
            "description": "Alters a target's behavior or allegiance.",
            "base_power": None,
            "base_anima_cost": 0,
            "has_power_scaling": False,
        },
    )
    technique, _created = Technique.objects.get_or_create(
        name=CHARM_TECHNIQUE_NAME,
        gift=charm_gift,
        defaults={
            "description": (
                "A word of power that turns an enemy's loyalty, charming them to fight for you."
            ),
            "style": style,
            "effect_type": effect_type,
            "action_category": ActionCategory.SOCIAL,
            "intensity": 4,
            "level": 1,
            "control": 4,
            "anima_cost": 2,
            "combo_opening_probing": None,
        },
    )
    charmed_template = ConditionTemplate.objects.get(name=CHARM_CONDITION_NAME)
    TechniqueAppliedCondition.objects.get_or_create(
        technique=technique,
        condition=charmed_template,
        target_kind=ConditionTargetKind.ENEMY,
        defaults={
            "base_severity": 1,
            "minimum_success_level": 1,
        },
    )
    return technique


def ensure_social_combat_content() -> None:
    """Idempotently seed the social-combat content (#2015).

    Seeds the 4 CheckTypes (Rally/Demoralize/Taunt/Parley) with stat + skill
    (+ spec) compositions, the ``Inspired`` condition, and the ``Charming Word``
    charm technique. Safe to call repeatedly — every write goes through
    ``get_or_create`` or the authoritative wipe-and-rewrite.
    """
    skills, specs = _ensure_social_skills_and_specs()
    _ensure_social_combat_check_types(skills, specs)
    _ensure_inspired_condition()
    _ensure_charm_technique()
