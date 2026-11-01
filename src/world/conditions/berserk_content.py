"""Production Berserk condition content (#2845, ADR-0171 config rows).

Every producer, the fury engine (`world.magic.services.fury.FuryCast.settle`)
and the moon control check (`world.species.moon_sensitivity`), finds Berserk
through `FuryConfig.berserk_condition` (#4739), never by name, so the seed points
an unset designation at the row it made. Until #2845 it existed only as a test factory
(`world.magic.factories.BerserkConditionTemplateFactory`, whose shape this
seed mirrors exactly) plus a gitignored local fixture whose copy sits in an
`alters_behavior=False` category and would silently fail to block form-revert.

`ensure_berserk_content` therefore also HEALS a pre-existing row: whatever
category a hand-loaded Berserk row landed in, it is re-anchored onto the
Control category so `CharacterSheet.in_control` derives False while raging.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.conditions.models import Compulsion, ConditionTemplate
    from world.traits.models import CheckOutcome

BERSERK_SEED_TEMPLATE_NAME = "Berserk"
CONTROL_CATEGORY_NAME = "Control"
COMPULSION_RESIST_CHECK_NAME = "Resist compulsion"


def ensure_berserk_content() -> None:
    """Idempotently seed (and heal) the Control category + Berserk template."""
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import (  # noqa: PLC0415
        ConditionCategory,
        ConditionStage,
        ConditionTemplate,
    )

    category, _ = ConditionCategory.objects.get_or_create(
        name=CONTROL_CATEGORY_NAME,
        defaults={
            "description": (
                "Conditions that change how a character behaves — compulsion, "
                "charm, fear, rage — rather than only their capabilities or stats."
            ),
            "is_negative": True,
            "alters_behavior": True,
            "display_order": 20,
        },
    )
    if not category.alters_behavior:
        category.alters_behavior = True
        category.save(update_fields=["alters_behavior"])

    template, _ = ConditionTemplate.objects.get_or_create(
        name=BERSERK_SEED_TEMPLATE_NAME,
        defaults={
            "category": category,
            "description": (
                "Lost to primal rage — unable to distinguish friend from foe, "
                "and unable to let go of the shape the rage wears."
            ),
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": 3,
            "has_progression": True,
            "is_stackable": False,
            "can_be_dispelled": False,
        },
    )
    if template.category_id != category.pk:
        template.category = category
        template.save(update_fields=["category"])

    ConditionStage.objects.get_or_create(
        condition=template,
        stage_order=1,
        defaults={
            "name": "Uncontrolled Rage",
            "description": (
                "Consumed by uncontrolled rage, lashing out at any target within reach."
            ),
            "rounds_to_next": None,
            "severity_multiplier": Decimal("1.00"),
        },
    )
    _designate_unset_berserk(template)
    ensure_restore_to_sense_effect(template)
    ensure_berserk_compulsion(template)


def _designate_unset_berserk(template: ConditionTemplate) -> None:
    """Point an unset ``FuryConfig.berserk_condition`` at the seeded template (#4739).

    A designation staff already set is never overwritten. The config row is made with
    its model defaults when absent, the same values the fury engine falls back to.
    """
    from world.magic.models import FuryConfig  # noqa: PLC0415

    config, _ = FuryConfig.objects.get_or_create(pk=1)
    if config.berserk_condition_id is None:
        config.berserk_condition = template
        config.save(update_fields=["berserk_condition"])


def ensure_restore_to_sense_effect(berserk_template: ConditionTemplate) -> None:
    """Seed the Restore-to-Sense removal effect targeting Berserk (#2845).

    The `restore_sense` Action and its remove-condition-on-check machinery have
    been wired since #567 but the production content never existed — only a
    test factory. This seeds the ActionEnhancement (sourced on the Berserk
    ConditionTemplate itself — the enhancement source only satisfies the
    one-FK constraint; dispatch is by ``base_action_key``) and the
    ``RemoveConditionOnCheckConfig`` rolling Persuasion. The "Restore to
    Sense" ActionTemplate row itself rides the social-actions seeder.
    """
    from actions.constants import EnhancementSourceType  # noqa: PLC0415
    from actions.models import ActionEnhancement  # noqa: PLC0415
    from actions.models.effect_configs import RemoveConditionOnCheckConfig  # noqa: PLC0415
    from world.checks.models import CheckType  # noqa: PLC0415

    check_type = CheckType.objects.filter(name="Persuasion", is_active=True).first()
    if check_type is None:
        return
    enhancement, _ = ActionEnhancement.objects.get_or_create(
        base_action_key="restore_sense",
        variant_name="Restore to Sense",
        defaults={
            "is_involuntary": False,
            "source_type": EnhancementSourceType.CONDITION,
            "condition": berserk_template,
        },
    )
    RemoveConditionOnCheckConfig.objects.get_or_create(
        enhancement=enhancement,
        condition=berserk_template,
        defaults={
            "check_type": check_type,
            "resistance_check_type": None,
            "target_difficulty": None,
            "execution_order": 0,
        },
    )


def ensure_compulsion_resist_check_type() -> CheckType:
    """Idempotently seed the "Resist compulsion" CheckType (#4802)."""
    return ensure_willpower_check_type(COMPULSION_RESIST_CHECK_NAME)


def ensure_willpower_check_type(name: str) -> CheckType:
    """Idempotently seed a willpower-led check type called *name* (#4802).

    Willpower at full weight, composure at half, in the Species category: the shape of
    both "Resist compulsion" and ``moon_control``. The row is found by name, so an
    authored one is reused; the weights are only written when the trait link is first
    made, so staff edits to an authored weight survive a re-run. A row made here carries
    no prose: its description, and the Species category's, are left for staff.
    """
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.traits.services import ensure_stat_trait  # noqa: PLC0415

    category, _ = CheckCategory.objects.get_or_create(
        name="Species",
        defaults={"description": "", "display_order": 97},
    )
    check_type, _ = CheckType.objects.get_or_create(
        name=name, defaults={"category": category, "description": ""}
    )
    for trait_name, weight in (("willpower", "1.00"), ("composure", "0.50")):
        CheckTypeTrait.objects.get_or_create(
            check_type=check_type,
            trait=ensure_stat_trait(trait_name),
            defaults={"weight": weight},
        )
    return check_type


def outcome_at_level(success_level: int) -> CheckOutcome:
    """The CheckOutcome at *success_level*, found by level and never by name (#4802).

    A missing tier is created at its canonical name, the same way every other seed does.
    """
    from world.traits.constants import CANONICAL_OUTCOME_LEVELS  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415
    from world.traits.services import ensure_canonical_check_outcome  # noqa: PLC0415

    existing = CheckOutcome.objects.filter(success_level=success_level).order_by("pk").first()
    if existing is not None:
        return existing
    name = next(n for n, level in CANONICAL_OUTCOME_LEVELS.items() if level == success_level)
    return ensure_canonical_check_outcome(name)


def ensure_berserk_compulsion(template: ConditionTemplate) -> Compulsion:
    """Idempotently seed Berserk's compulsion, its forbidden actions and resist bands (#4802).

    The rage drives the bearer to attack; fleeing, parleying, leaving the fight and
    reverting form each need a resist roll, harder than the base. A compulsion staff
    already authored is returned untouched: its forbidden actions and bands are theirs.
    """
    from world.conditions.constants import (  # noqa: PLC0415
        CompulsionForbidden,
        CompulsionResult,
        CompulsionWant,
    )
    from world.conditions.models import (  # noqa: PLC0415
        Compulsion,
        CompulsionForbiddenAction,
        CompulsionResistBand,
    )

    compulsion, created = Compulsion.objects.get_or_create(
        condition=template,
        defaults={
            "wants": CompulsionWant.ATTACK_OPPONENT,
            "check_type": ensure_compulsion_resist_check_type(),
            "base_difficulty": 25,
            "difficulty_per_severity": 2,
            "retry_wait_minutes": 5,
        },
    )
    if not created:
        return compulsion
    for action, extra in (
        (CompulsionForbidden.FLEE, 5),
        (CompulsionForbidden.PARLEY, 5),
        (CompulsionForbidden.LEAVE, 10),
        (CompulsionForbidden.REVERT_FORM, 10),
    ):
        CompulsionForbiddenAction.objects.get_or_create(
            compulsion=compulsion, action=action, defaults={"extra_difficulty": extra}
        )
    # (success_level, result, action_penalty, control_change). The failures carry the
    # strained penalty too: a better outcome may never be worse for the bearer, and the
    # penalty is moot once the compulsion acts in place of the declaration.
    for level, result, penalty, control in (
        (2, CompulsionResult.ACTS_FREELY, 0, 0),
        (1, CompulsionResult.ACTS_FREELY, 0, 0),
        (0, CompulsionResult.ACTS_STRAINED, 4, -2),
        (-1, CompulsionResult.COMPULSION_ACTS, 4, -2),
        (-2, CompulsionResult.COMPULSION_ACTS, 4, -4),
    ):
        CompulsionResistBand.objects.get_or_create(
            compulsion=compulsion,
            outcome=outcome_at_level(level),
            defaults={"result": result, "action_penalty": penalty, "control_change": control},
        )
    return compulsion
