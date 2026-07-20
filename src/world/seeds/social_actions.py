"""Production seed for the social ActionTemplates + their consequence effects (#1697).

Until now the social ActionTemplates (Intimidate / Persuade / Deceive / Flirt / Perform / Entrance)
and their consequence pools existed only in test fixtures (``checks/factories.py`` /
``world/seeds/game_content``) — nothing seeded them authoritatively, so a successful flirt set
no relationship state in production. This is the authoritative, idempotent (plain-ORM) production
seed. It also attaches the **directed-allure write side**: a successful **Flirt** sets the target
**Attracted To** the actor (permanent) + **Very Attracted** (temporary) via the merged
``SET_RELATIONSHIP_CONDITION`` effect, so the actor's allure rides future social rolls against them.

Seduce + its +1-difficulty knob + the Smitten application on Seduce are layered on top (#1697).
Magnitudes/durations are PLACEHOLDER. Runs after the ``social`` (check) + ``social_relationships``
(allure target + Attracted/Very-Attracted conditions) clusters.
"""

from __future__ import annotations

from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# (template_name, check_type_name, target_type, icon, difficulty_tier_modifier).
# Seduce reuses the Seduction check but rolls one tier harder than Flirt (#1697).
_SOCIAL_ACTION_TEMPLATES = [
    ("Intimidate", "Intimidation", "single", "skull", 0),
    # Blackmail reuses the Intimidation check (coercion by threat), gated by the
    # `blackmail` consent category and resolved by the defender's plausibility band; on
    # success BlackmailAction mints Leverage founded on the pressed secret (#1680).
    ("Blackmail", "Intimidation", "single", "lock", 0),
    ("Persuade", "Persuasion", "single", "handshake", 0),
    # Boon (#2540): the structured social ask — a named payload (money / held item / vault
    # item / deed) riding the request, gated by the `boon` consent category; fulfillment
    # fires via the `boon` action resolver on a successful roll. Reuses the Persuasion
    # check; the con/seduce/intimidate ask flavors are a follow-up slice.
    ("Boon", "Persuasion", "single", "gift", 0),
    ("Deceive", "Deceive", "single", "mask", 0),
    ("Flirt", "Seduction", "single", "heart", 0),
    ("Seduce", "Seduction", "single", "flame", 1),
    ("Perform", "Performance", "area", "music", 0),
    ("Entrance", "Presence", "area", "sparkles", 0),
]
_ENTRANCE_TEMPLATE_NAME = "Entrance"
_POOL_PREFIX = "Social"

# (outcome_tier_name, label, weight) per action — the three standard tiers.
_POOL_CONSEQUENCES: dict[str, list[tuple[str, str, int]]] = {
    "Intimidate": [
        ("Failure", "Intimidation falls flat", 1),
        ("Partial Success", "Target rattled but holds firm", 2),
        ("Success", "Target cowed and compliant", 1),
    ],
    "Blackmail": [
        ("Failure", "The threat rings hollow", 1),
        ("Partial Success", "They waver, but call your bluff", 2),
        ("Success", "They fold under the threat", 1),
    ],
    "Persuade": [
        ("Failure", "Argument dismissed outright", 1),
        ("Partial Success", "Target intrigued but unconvinced", 2),
        ("Success", "Target fully persuaded", 1),
    ],
    "Boon": [
        ("Failure", "The ask lands badly", 1),
        ("Partial Success", "They hesitate, unmoved", 2),
        ("Success", "They grant the boon", 1),
    ],
    "Deceive": [
        ("Failure", "Lie detected immediately", 1),
        ("Partial Success", "Partial deception holds", 2),
        ("Success", "Target completely deceived", 1),
    ],
    "Flirt": [
        ("Failure", "Advance rebuffed", 1),
        ("Partial Success", "Interest piqued but guarded", 2),
        ("Success", "Charm lands completely", 1),
    ],
    "Seduce": [
        ("Failure", "Seduction rebuffed", 1),
        ("Partial Success", "Tempted but resistant", 2),
        ("Success", "Swept off their feet", 1),
    ],
    "Perform": [
        ("Failure", "Performance falls flat", 1),
        ("Partial Success", "Audience politely attentive", 2),
        ("Success", "Audience captivated", 1),
    ],
    "Entrance": [
        ("Failure", "Entrance goes unnoticed", 1),
        ("Partial Success", "Attention caught briefly", 2),
        ("Success", "All eyes arrested", 1),
    ],
}
_SUCCESS_TIER = "Success"

# PLACEHOLDER: Very Attracted lasts to end of scene OR ~2 IC days, whichever first (#1697). The
# scene-end clear (Scene.finish_scene → clear_very_attracted) is the primary path; this real-time
# cap (≈2 IC days at the default 3:1 ratio) is the backstop for out-of-scene / long scenes.
VERY_ATTRACTED_DURATION = timedelta(hours=16)

SMITTEN_CONDITION_NAME = "Smitten"

# Smitten's mechanical package (#1697) — all PLACEHOLDER magnitudes pending tuning.
_SMITTEN_EXPLOITABLE_TIERS = 2
_SMITTEN_DEFENSE_PENALTY = -10
_SMITTEN_DAMAGE_TYPE = "Force"
_SMITTEN_DAMAGE_BONUS_PCT = 100
_MELEE_DEFENSE_CHECK_NAME = "Melee Defense"

# Automatic affection shifts on success (#1697) — the first instances of the generic
# valence-signed SHIFT_AFFECTION family. PLACEHOLDER magnitudes (#1699 scale: bump 1,
# flirt 5, seduction 50, capstone 250). First-per-scene-per-pair dedup lives in
# relationships.AffectionShift.
FLIRT_AFFECTION_SHIFT = 5
SEDUCE_AFFECTION_SHIFT = 50


def _success_consequence(action_name: str):
    """Get-or-create the Success-tier Consequence for an action's pool, returning it + the pool."""
    from actions.models import ConsequencePool, ConsequencePoolEntry  # noqa: PLC0415
    from world.checks.models import Consequence  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    pool, _ = ConsequencePool.objects.get_or_create(
        name=f"{_POOL_PREFIX}: {action_name}",
        defaults={"description": f"Consequence pool for the {action_name} social action."},
    )
    success = None
    for outcome_name, label, weight in _POOL_CONSEQUENCES[action_name]:
        outcome, _ = CheckOutcome.objects.get_or_create(name=outcome_name)
        consequence, _ = Consequence.objects.get_or_create(
            outcome_tier=outcome, label=label, defaults={"weight": weight, "character_loss": False}
        )
        ConsequencePoolEntry.objects.get_or_create(pool=pool, consequence=consequence)
        if outcome_name == _SUCCESS_TIER:
            success = consequence
    return pool, success


def ensure_social_action_templates() -> dict[str, object]:
    """Seed the social ActionTemplates + their consequence pools (authoritative, idempotent)."""
    from actions.models import ActionTemplate  # noqa: PLC0415
    from world.checks.models import CheckType  # noqa: PLC0415

    templates: dict[str, object] = {}
    for name, check_type_name, target_type, icon, tier_modifier in _SOCIAL_ACTION_TEMPLATES:
        check_type = CheckType.objects.filter(name=check_type_name).first()
        if check_type is None:
            # The check isn't seeded — "Presence" (Entrance) is a deliberate placeholder the
            # social-check retrofit omits (#1690). Skip until it's defined rather than recreate the
            # old stat+stat row.
            logger.warning(
                "Skipping social action template %r: CheckType %r is not seeded.",
                name,
                check_type_name,
            )
            continue
        pool, _success = _success_consequence(name)
        template, _ = ActionTemplate.objects.get_or_create(
            name=name,
            defaults={
                "check_type": check_type,
                "consequence_pool": pool,
                "target_type": target_type,
                "icon": icon,
                "category": "social",
                "grants_entry_flourish": name == _ENTRANCE_TEMPLATE_NAME,
                "difficulty_tier_modifier": tier_modifier,
            },
        )
        # get_or_create won't update an existing row — keep pool/check_type/tier wired.
        if (
            template.consequence_pool_id != pool.pk
            or template.check_type_id != check_type.pk
            or template.difficulty_tier_modifier != tier_modifier
        ):
            template.consequence_pool = pool
            template.check_type = check_type
            template.difficulty_tier_modifier = tier_modifier
            template.save(
                update_fields=["consequence_pool", "check_type", "difficulty_tier_modifier"]
            )
        templates[name] = template
    return templates


def ensure_smitten_condition():
    """The social ``Smitten`` condition seduction applies, with its teeth (#1697).

    A distinct social condition (the combat ``Vulnerable`` owns that name). The
    mechanical package (all PLACEHOLDER magnitudes pending tuning):

    - ``exploitable_tiers=2`` — checks rolled AGAINST a Smitten bearer resolve two
      difficulty tiers easier (the seduce-then-strike seam,
      ``world.scenes.social_difficulty``).
    - A ``ConditionCheckModifier`` penalizing the bearer's Melee Defense — they
      defend worse while captivated.
    - A ``ConditionDamageInteraction`` boosting Force damage against the bearer
      (rides the #2018 wiring), keyed to Force (the physical damage type).

    The condition-scoped modifier package (defense penalty + damage amplification
    + tier easing) IS the surprise-attack mechanic — no separate combat primitive
    is needed. Ratified in #2241: the shipped shape is the final shape.

    Applied by Seduce, not Flirt. Field updates are explicit writes / upserts so
    re-seeding applies edits (#946).
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.conditions.models import (  # noqa: PLC0415
        ConditionCategory,
        ConditionCheckModifier,
        ConditionDamageInteraction,
        ConditionTemplate,
        DamageType,
    )

    category, _ = ConditionCategory.objects.get_or_create(
        name="Social",
        defaults={"description": "Social / emotional states that color interaction."},
    )
    template, _ = ConditionTemplate.objects.get_or_create(
        name=SMITTEN_CONDITION_NAME,
        defaults={
            "category": category,
            "description": "Emotionally captivated by the seducer — more open to their influence.",
        },
    )
    if template.exploitable_tiers != _SMITTEN_EXPLOITABLE_TIERS:
        template.exploitable_tiers = _SMITTEN_EXPLOITABLE_TIERS
        template.save(update_fields=["exploitable_tiers"])

    defense_check = CheckType.objects.filter(name=_MELEE_DEFENSE_CHECK_NAME).first()
    if defense_check is not None:
        ConditionCheckModifier.objects.update_or_create(
            condition=template,
            check_type=defense_check,
            defaults={"modifier_value": _SMITTEN_DEFENSE_PENALTY},
        )
    else:
        logger.warning("Melee Defense CheckType not seeded; Smitten defense penalty skipped.")

    force = DamageType.objects.filter(name=_SMITTEN_DAMAGE_TYPE).first()
    if force is not None:
        ConditionDamageInteraction.objects.update_or_create(
            condition=template,
            damage_type=force,
            defaults={"damage_modifier_percent": _SMITTEN_DAMAGE_BONUS_PCT},
        )
    else:
        logger.warning(
            "%s DamageType not seeded; Smitten damage row skipped.", _SMITTEN_DAMAGE_TYPE
        )
    return template


def _attach_attraction_effects(
    consequence, *, include_smitten: bool, affection_shift: int = 0
) -> None:
    """Attach the directed-allure write effects to a success Consequence (#1697).

    Sets the TARGET **Attracted To** the actor (permanent) + **Very Attracted** (temporary). When
    ``include_smitten`` (Seduce), also applies the Smitten condition. A nonzero
    ``affection_shift`` attaches the SHIFT_AFFECTION effect — the automatic
    target→actor regard shift (first-per-scene-per-pair; the first instances of
    the generic valence-signed shift family). Idempotent + upserting.
    """
    from world.checks.constants import EffectTarget, EffectType  # noqa: PLC0415
    from world.checks.models import ConsequenceEffect  # noqa: PLC0415
    from world.relationships.models import RelationshipCondition  # noqa: PLC0415
    from world.seeds.social_relationships import (  # noqa: PLC0415
        ATTRACTED_CONDITION_NAME,
        VERY_ATTRACTED_CONDITION_NAME,
    )

    attracted = RelationshipCondition.objects.get(name=ATTRACTED_CONDITION_NAME)
    very = RelationshipCondition.objects.get(name=VERY_ATTRACTED_CONDITION_NAME)

    ConsequenceEffect.objects.get_or_create(
        consequence=consequence,
        effect_type=EffectType.SET_RELATIONSHIP_CONDITION,
        relationship_condition=attracted,
        defaults={"target": EffectTarget.TARGET, "execution_order": 0},
    )
    ConsequenceEffect.objects.get_or_create(
        consequence=consequence,
        effect_type=EffectType.SET_RELATIONSHIP_CONDITION,
        relationship_condition=very,
        defaults={
            "target": EffectTarget.TARGET,
            "execution_order": 1,
            "relationship_condition_duration": VERY_ATTRACTED_DURATION,
        },
    )
    if include_smitten:
        ConsequenceEffect.objects.get_or_create(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=ensure_smitten_condition(),
            defaults={
                "target": EffectTarget.TARGET,
                "execution_order": 2,
                "condition_severity": 1,
            },
        )
    if affection_shift:
        ConsequenceEffect.objects.update_or_create(
            consequence=consequence,
            effect_type=EffectType.SHIFT_AFFECTION,
            defaults={
                "target": EffectTarget.TARGET,
                "execution_order": 3,
                "affection_amount": affection_shift,
            },
        )


def seed_social_action_content() -> None:
    """Cluster entry — seed social ActionTemplates + pools + Flirt/Seduce attraction effects."""
    ensure_social_action_templates()
    _, flirt_success = _success_consequence("Flirt")
    _attach_attraction_effects(
        flirt_success, include_smitten=False, affection_shift=FLIRT_AFFECTION_SHIFT
    )
    # Seduce: same attraction, plus the Smitten condition (a deeper hold) — and it rolls one tier
    # harder than Flirt (difficulty_tier_modifier=1, set on the template above).
    _, seduce_success = _success_consequence("Seduce")
    _attach_attraction_effects(
        seduce_success, include_smitten=True, affection_shift=SEDUCE_AFFECTION_SHIFT
    )
