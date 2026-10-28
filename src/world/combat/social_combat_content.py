"""Social-combat content seed (#2015).

Idempotently seeds the content the four social/mental combat verbs need:

* Four ``CheckType`` rows (Rally/Demoralize/Taunt/Parley) with stat + skill
  (+ specialization) compositions, reusing the social skills/specializations
  seeded by ``world.seeds.social_checks`` (``ensure_social_skills`` /
  ``ensure_social_specializations``). ``checks.CheckCategory``/``CheckType``/
  ``CheckTypeTrait`` are content-repo-owned (#2698) — looked up via
  ``authored_or_sample()`` rather than invented unless ``SEED_SAMPLE_CONTENT``
  is on; a reseed no longer wipes and rewrites the composition (#2698 Part 1).
* An ``Inspired`` ``ConditionTemplate`` (``alters_behavior=False``) — the
  short-lived benefit ``RALLY`` applies to an ally, consumed by the ally's
  next resolved action this round. Mirrors ``conditions/charm_content.py``.
* ``SocialManeuverConfig`` (#4739): each designation still unset is pointed at
  the row just seeded (Taunt/Demoralize/Parley check types, Inspired as Rally's
  success condition); a designation staff already set is left alone. Rally's
  check is the ``RALLIED`` ``SurgeTuning``'s, which this seed does not author.
* A ``Charming Word`` ``Technique`` carrying a ``TechniqueAppliedCondition``
  targeting ``ENEMY`` with the already-seeded ``Charmed`` template — so the
  Charm → allegiance flip (``derive_allegiance`` → ``ALLY_OF_CASTER``) is
  player-reachable without requiring the parley verb. Mirrors the technique
  seed pattern in ``combat/defend_content.py``.

``ensure_social_combat_content`` is idempotent (all writes via ``get_or_create``
or ``authored_or_sample``) and doubles as integration-test setup and staff
seed data. Safe to call repeatedly.
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
)

if TYPE_CHECKING:
    from world.checks.models import CheckCategory, CheckType
    from world.traits.models import Trait

# Identity keys for the seed only (#4739): the game finds Inspired and the verb checks by
# their SocialManeuverConfig designation, never by name; nothing outside seeds, factories
# and tests imports these.
INSPIRED_SEED_TEMPLATE_NAME: str = "Inspired"
CHARM_TECHNIQUE_NAME: str = "Charming Word"
RALLY_SEED_CHECK_NAME: str = "Rally"
DEMORALIZE_SEED_CHECK_NAME: str = "Demoralize"
TAUNT_SEED_CHECK_NAME: str = "Taunt"
PARLEY_SEED_CHECK_NAME: str = "Parley"

# (check_type_name, stat_trait_name, skill_name, specialization_name | None).
# Reuses the social skills/specializations from seeds/social_checks.py:
# Persuasion + (Intimidation/Seduction) specs, Performance + Oratory spec.
# Taunt rolls wits + Persuasion + Intimidation (a provoking jab).
_SOCIAL_COMBAT_COMPOSITION: tuple[tuple[str, str, str, str | None], ...] = (
    (RALLY_SEED_CHECK_NAME, "presence", "Performance", "Oratory"),
    (DEMORALIZE_SEED_CHECK_NAME, "presence", "Persuasion", "Intimidation"),
    (TAUNT_SEED_CHECK_NAME, "wits", "Persuasion", "Intimidation"),
    (PARLEY_SEED_CHECK_NAME, "charm", "Persuasion", "Seduction"),
)


def _ensure_social_category() -> CheckCategory | None:
    """Look up (or sample) the Social CheckCategory — content-repo-owned (#2698)."""
    from world.checks.models import CheckCategory  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    return authored_or_sample(
        CheckCategory,
        {
            "description": "Checks involving social interaction, persuasion, and presence.",
            "display_order": 10,
        },
        name="Social",
    )


def _ensure_stat_trait(name: str) -> Trait | None:
    """Look up (or sample) a SOCIAL stat Trait — content-repo-owned (#2698)."""
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    return authored_or_sample(
        Trait,
        {
            "trait_type": TraitType.STAT,
            "category": TraitCategory.SOCIAL,
            "is_public": True,
        },
        name=name,
    )


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
) -> dict[str, CheckType]:
    """Seed the 4 social-combat CheckTypes with stat + skill (+ spec) composition.

    ``checks.CheckCategory``/``CheckType``/``CheckTypeTrait`` are content-repo-owned
    (#2698) — looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on.
    No longer wipes and rewrites the composition on each run (#2698 Part 1 — that
    reverted any authored/staff-tuned weight on every Big Button press);
    ``get_or_create``/``authored_or_sample`` converge instead, preserving edits.
    ``CheckTypeSpecialization`` stays outside ``CONTENT_MODELS`` and keeps
    seeding unconditionally. A CheckType whose category or row isn't authored is
    skipped entirely for that entry.
    """
    from world.checks.models import (  # noqa: PLC0415
        CheckType,
        CheckTypeSpecialization,
        CheckTypeTrait,
    )
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    category = _ensure_social_category()
    weight = Decimal("1.0")  # PLACEHOLDER magnitudes
    check_types: dict[str, CheckType] = {}
    if category is None:
        return check_types

    for ct_name, stat_name, skill_name, spec_name in _SOCIAL_COMBAT_COMPOSITION:
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
        if spec_name is not None and specs.get(spec_name) is not None:
            CheckTypeSpecialization.objects.get_or_create(
                check_type=check_type, specialization=specs[spec_name], defaults={"weight": weight}
            )
        check_types[ct_name] = check_type
    return check_types


def _ensure_inspired_condition() -> ConditionTemplate | None:
    """Seed the ``Inspired`` condition category + template (#2015).

    A short-lived benefit RALLY applies to an ally. ``alters_behavior=False`` —
    it is a buff, not a compulsion (ADR-0024: consent gates behavior-alteration,
    not benefit). Duration: 1 round (consumed by the ally's next resolved action).

    ``conditions.ConditionCategory``/``ConditionTemplate`` are content-repo-owned
    (#2698) — looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on.
    """
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    category = authored_or_sample(
        ConditionCategory,
        {
            "description": "Rallying and inspirational effects that bolster allies.",
            "is_negative": False,
            "alters_behavior": False,
        },
        name="Inspiration",
    )
    return authored_or_sample(
        ConditionTemplate,
        {
            "category": category,
            "description": "Inspired by an ally's rallying words; the next action lands harder.",
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": 1,
            "is_stackable": False,
            "can_be_dispelled": True,
        },
        name=INSPIRED_SEED_TEMPLATE_NAME,
    )


def _ensure_charm_technique() -> Technique | None:
    """Seed the ``Charming Word`` technique that applies Charmed to an ENEMY (#2015).

    Makes the Charm → allegiance flip (``derive_allegiance`` → ``ALLY_OF_CASTER``)
    player-reachable without the parley verb. Mirrors the technique seed in
    ``combat/defend_content.py``: direct ORM lookups, not the budget builder.

    ``Gift``/``EffectType``/``Technique``/
    ``TechniqueAppliedCondition`` are all content-repo-owned (#2698) — looked
    up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on. Returns
    ``None`` (skipping the TechniqueAppliedCondition row) when any
    prerequisite is missing. The ``Charmed`` ConditionTemplate this technique
    applies (``conditions.conditiontemplate``) is ALSO content-repo-owned
    (#2698) — ``ensure_charm_content()`` now gates its own creation, so this
    looks it up defensively rather than assuming it exists.
    """
    # Ensure the Charmed template exists first (self-contained seed).
    from world.conditions.charm_content import ensure_charm_content  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    ensure_charm_content()
    charm_gift = authored_or_sample(
        Gift,
        {"description": "Charm, compulsion, and social influence magic."},
        name="Charm",
    )
    effect_type = authored_or_sample(
        EffectType,
        {
            "description": "Alters a target's behavior or allegiance.",
            "base_power": None,
            "base_anima_cost": 0,
            "has_power_scaling": False,
        },
        name="Compulsion",
    )
    if charm_gift is None or effect_type is None:
        return None

    technique = authored_or_sample(
        Technique,
        {
            "description": (
                "A word of power that turns an enemy's loyalty, charming them to fight for you."
            ),
            "effect_type": effect_type,
            "action_category": ActionCategory.SOCIAL,
            "intensity": 4,
            "level": 1,
            "control": 4,
            "anima_cost": 2,
            "combo_opening_probing": None,
        },
        name=CHARM_TECHNIQUE_NAME,
        gift=charm_gift,
    )
    if technique is None:
        return None

    charmed_template = ConditionTemplate.objects.filter(name=CHARM_CONDITION_NAME).first()
    if charmed_template is None:
        return technique
    authored_or_sample(
        TechniqueAppliedCondition,
        {
            "base_severity": 1,
            "minimum_success_level": 1,
        },
        technique=technique,
        condition=charmed_template,
        target_kind=ConditionTargetKind.ENEMY,
    )
    return technique


def _designate_unset(check_types: dict[str, CheckType], inspired: ConditionTemplate | None) -> None:
    """Point each unset ``SocialManeuverConfig`` designation at the row just seeded (#4739).

    A designation staff already set is never overwritten (precedent: the Soulfray seed in
    ``world/magic/factories.py``). A row the seed skipped (not authored) leaves its
    designation unset for the Required content dashboard to list.
    """
    from world.combat.services.encounter.config import (  # noqa: PLC0415
        get_social_maneuver_config,
    )

    config = get_social_maneuver_config()
    taunt = check_types.get(TAUNT_SEED_CHECK_NAME)
    demoralize = check_types.get(DEMORALIZE_SEED_CHECK_NAME)
    parley = check_types.get(PARLEY_SEED_CHECK_NAME)
    changed: list[str] = []
    if taunt is not None and config.taunt_check_type_id is None:
        config.taunt_check_type = taunt
        changed.append("taunt_check_type")
    if demoralize is not None and config.demoralize_check_type_id is None:
        config.demoralize_check_type = demoralize
        changed.append("demoralize_check_type")
    if parley is not None and config.parley_check_type_id is None:
        config.parley_check_type = parley
        changed.append("parley_check_type")
    if inspired is not None and config.rally_success_condition_id is None:
        config.rally_success_condition = inspired
        changed.append("rally_success_condition")
    if changed:
        config.save(update_fields=changed)


def ensure_social_combat_content() -> None:
    """Idempotently seed the social-combat content (#2015).

    Seeds the 4 CheckTypes (Rally/Demoralize/Taunt/Parley) with stat + skill
    (+ spec) compositions, the ``Inspired`` condition, and the ``Charming Word``
    charm technique, then points any unset ``SocialManeuverConfig`` designation at
    the seeded rows (#4739). Safe to call repeatedly — every write goes through
    ``get_or_create`` or ``authored_or_sample``, and a set designation is kept.
    """
    skills, specs = _ensure_social_skills_and_specs()
    check_types = _ensure_social_combat_check_types(skills, specs)
    inspired = _ensure_inspired_condition()
    _designate_unset(check_types, inspired)
    _ensure_charm_technique()
