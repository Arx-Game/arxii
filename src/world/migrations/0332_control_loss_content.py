"""Carry today's Berserk and moon-control behavior into the new rows (#4802).

Data-only. On a populated database it:

* gives Berserk (found through ``FuryConfig.berserk_condition``) its compulsion;
* makes the ``moon_control`` CheckType and the "Lycan blood" condition;
* sets Lycan blood as the lycan gift grant's ``drawback_condition`` and puts an
  instance of it on every sheet holding a distinction tagged ``moon-bound``;
* seeds the moon-pull control-loss trigger and its bands.

Idempotent, and a no-op on an empty database: every step hangs off a row that only a
populated database has. The values mirror ``berserk_content.ensure_berserk_compulsion``
and ``moon_provisioning.ensure_moon_control_loss_trigger``, which new databases use.
"""

from django.db import migrations

# The one-time name and slug resolutions. Runtime code finds these rows by foreign key
# and designation; this migration is the only place that resolves them from today's
# literals, because nothing else links an existing lycan or moon-bound character yet.
LYCAN_GIFT_NAME = "The Wolf's Fury"
MOON_BOUND_TAG_SLUG = "moon-bound"

CANONICAL_OUTCOMES = {
    2: "Critical Success",
    1: "Success",
    0: "Partial Success",
    -1: "Failure",
    -2: "Critical Failure",
}
# name -> (category, description) of the STAT traits the checks weigh, as
# world.traits.constants.STAT_TRAIT_DEFAULTS holds them.
STAT_TRAITS = {
    "willpower": ("meta", "Mental fortitude and determination."),
    "composure": (
        "social",
        "Social endurance. Poise under social pressure and resistance to embarrassment.",
    ),
}


def _outcome(apps, success_level):
    """The CheckOutcome at *success_level*, found by level (created if the tier is missing)."""
    CheckOutcome = apps.get_model("arxii", "CheckOutcome")
    existing = CheckOutcome.objects.filter(success_level=success_level).order_by("pk").first()
    if existing is not None:
        return existing
    outcome, _ = CheckOutcome.objects.get_or_create(
        name=CANONICAL_OUTCOMES[success_level], defaults={"success_level": success_level}
    )
    return outcome


def _check_type(apps, name, description):
    """The willpower (1.0) plus composure (0.5) check type called *name*."""
    CheckCategory = apps.get_model("arxii", "CheckCategory")
    CheckType = apps.get_model("arxii", "CheckType")
    CheckTypeTrait = apps.get_model("arxii", "CheckTypeTrait")
    Trait = apps.get_model("arxii", "Trait")

    check_type = CheckType.objects.filter(name=name).first()
    if check_type is None:
        category, _ = CheckCategory.objects.get_or_create(
            name="Species",
            defaults={"description": "Species instinct-control checks", "display_order": 97},
        )
        check_type = CheckType.objects.create(name=name, category=category, description=description)
    for trait_name, weight in (("willpower", "1.00"), ("composure", "0.50")):
        trait_category, trait_description = STAT_TRAITS[trait_name]
        trait, _ = Trait.objects.get_or_create(
            name=trait_name,
            defaults={
                "trait_type": "stat",
                "category": trait_category,
                "description": trait_description,
            },
        )
        CheckTypeTrait.objects.get_or_create(
            check_type=check_type, trait=trait, defaults={"weight": weight}
        )
    return check_type


def _berserk_compulsion(apps):
    FuryConfig = apps.get_model("arxii", "FuryConfig")
    Compulsion = apps.get_model("arxii", "Compulsion")
    ForbiddenAction = apps.get_model("arxii", "CompulsionForbiddenAction")
    ResistBand = apps.get_model("arxii", "CompulsionResistBand")

    config = FuryConfig.objects.filter(berserk_condition__isnull=False).first()
    if config is None:
        return None
    compulsion, _ = Compulsion.objects.get_or_create(
        condition_id=config.berserk_condition_id,
        defaults={
            "wants": "attack_opponent",
            "check_type": _check_type(
                apps, "compulsion_resist", "Holding the self against a compulsion (#4802)."
            ),
            "base_difficulty": 25,
            "difficulty_per_severity": 2,
        },
    )
    for action, extra in (("flee", 5), ("parley", 5), ("leave", 10), ("revert_form", 10)):
        ForbiddenAction.objects.get_or_create(
            compulsion=compulsion, action=action, defaults={"extra_difficulty": extra}
        )
    for level, result, penalty, control in (
        (2, "acts_freely", 0, 0),
        (1, "acts_freely", 0, 0),
        (0, "acts_strained", 4, -2),
        (-1, "compulsion_acts", 4, -2),
        (-2, "compulsion_acts", 4, -4),
    ):
        ResistBand.objects.get_or_create(
            compulsion=compulsion,
            outcome=_outcome(apps, level),
            defaults={"result": result, "action_penalty": penalty, "control_change": control},
        )
    return config.berserk_condition


def _lycan_blood(apps, grant):
    """The grant's drawback condition, making and setting Lycan blood when it has none."""
    ConditionCategory = apps.get_model("arxii", "ConditionCategory")
    ConditionTemplate = apps.get_model("arxii", "ConditionTemplate")

    if grant.drawback_condition_id is not None:
        return grant.drawback_condition
    category, _ = ConditionCategory.objects.get_or_create(
        name="Instinct",
        defaults={"description": "Instinctive species states.", "is_negative": False},
    )
    blood, _ = ConditionTemplate.objects.get_or_create(
        name="Lycan blood",
        defaults={
            "category": category,
            "description": "PLACEHOLDER: the blood remembers the moon (#4802).",
            "default_duration_type": "permanent",
            "is_stackable": False,
            "can_be_dispelled": False,
        },
    )
    grant.drawback_condition = blood
    grant.save(update_fields=["drawback_condition"])
    return blood


def _moon_bearers(apps, blood):
    """An instance of *blood* on every sheet holding a distinction tagged moon-bound."""
    CharacterDistinction = apps.get_model("arxii", "CharacterDistinction")
    ConditionInstance = apps.get_model("arxii", "ConditionInstance")

    # A character sheet shares its pk with the character's ObjectDB row.
    sheet_ids = set(
        CharacterDistinction.objects.filter(
            distinction__tags__slug=MOON_BOUND_TAG_SLUG
        ).values_list("character_id", flat=True)
    )
    already = set(
        ConditionInstance.objects.filter(condition=blood, target_id__in=sheet_ids).values_list(
            "target_id", flat=True
        )
    )
    ConditionInstance.objects.bulk_create(
        [ConditionInstance(target_id=pk, condition=blood) for pk in sorted(sheet_ids - already)]
    )


def _moon_trigger(apps, grant, blood, berserk):
    ControlLossTrigger = apps.get_model("arxii", "ControlLossTrigger")
    ControlLossBand = apps.get_model("arxii", "ControlLossBand")

    trigger, _ = ControlLossTrigger.objects.get_or_create(
        vulnerability=blood,
        fires_on="moon_pull",
        defaults={
            "min_moon_pull": 6,
            "check_type": _check_type(
                apps, "moon_control", "Holding the self against the moon's pull (#2845)."
            ),
            "base_difficulty": 20,
            "difficulty_per_pull": 5,
            "relief_per_level": 10,
            "relief_gift_id": grant.gift_id,
            "relief_per_thread_level": 5,
            "relief_cap": 30,
            "exempt_from_level": 6,
            "impaired_willpower_drop": 10,
        },
    )
    for level in (2, 1, 0, -1, -2):
        failed = level < 0
        ControlLossBand.objects.get_or_create(
            trigger=trigger,
            outcome=_outcome(apps, level),
            defaults=(
                {"applies": berserk, "severity": 3, "duration_rounds": 3, "forces_form": True}
                if failed
                else {}
            ),
        )


def seed_control_loss_content(apps, schema_editor):
    SpeciesGiftGrant = apps.get_model("arxii", "SpeciesGiftGrant")

    berserk = _berserk_compulsion(apps)
    grant = SpeciesGiftGrant.objects.filter(gift__name=LYCAN_GIFT_NAME).first()
    if grant is None:
        return
    blood = _lycan_blood(apps, grant)
    _moon_bearers(apps, blood)
    if berserk is not None:
        _moon_trigger(apps, grant, blood, berserk)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0331_control_loss_compulsion"),
    ]

    operations = [
        migrations.RunPython(seed_control_loss_content, migrations.RunPython.noop),
    ]
