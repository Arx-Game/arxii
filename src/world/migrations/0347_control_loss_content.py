"""Carry today's code-held Berserk and moon-control tuning into the new rows (#4802).

Data-only, and only prose-free mechanics. On a populated database it:

* gives Berserk (found through ``FuryConfig.berserk_condition``) its compulsion, unless
  Berserk already has one;
* for the lycan gift grant with no ``drawback_condition``: makes a "Lycan blood" nameplate
  condition (permanent, no prose), sets it as the grant's drawback, puts an instance of it
  on every sheet holding a distinction tagged ``moon-bound``, and seeds the moon-pull
  trigger and its bands, rolled on an existing "moon_control" CheckType if there is one,
  else on "Hold against the moon" (its player-facing name; found or made), unless a
  moon-pull trigger already exists;
* for a grant whose drawback has no moon-pull trigger (a rollback and re-apply leaves
  exactly this): seeds the trigger and its bands on that drawback, and nothing else. No
  instance is ever put on a drawback this migration did not just create.

A drawback that already has a moon-pull trigger is left entirely alone. An existing
compulsion or trigger is never added to, and no existing value is overwritten: the only
write to an existing row fills the lycan grant's unset drawback. Every row made here
carries no prose (empty descriptions), and no trait is ever created. The "Required content" probes "Berserk has a
compulsion" and "a moon's-pull control-loss trigger exists" report anything this
skipped. Idempotent, and a no-op on an empty database.
"""

from django.db import migrations

# The one-time name and slug resolutions. Runtime code finds these rows by foreign key
# and designation; this migration is the only place that resolves them from today's
# literals, because nothing else links an existing lycan or moon-bound character yet.
LYCAN_GIFT_NAME = "The Wolf's Fury"
MOON_BOUND_TAG_SLUG = "moon-bound"

# world.traits.constants.CANONICAL_OUTCOME_LEVELS, copied: a migration never imports live
# code. Outcomes are found by these names; a level alone is not unique.
CANONICAL_OUTCOME_LEVELS = {
    "Critical Failure": -2,
    "Failure": -1,
    "Partial Success": 0,
    "Success": 1,
    "Critical Success": 2,
}
OUTCOME_NAME_AT_LEVEL = {level: name for name, level in CANONICAL_OUTCOME_LEVELS.items()}


def _outcome(apps, success_level):
    """The canonical CheckOutcome for *success_level*, found by its canonical name.

    Created at that level when the tier is missing, the way
    ``ensure_canonical_check_outcome`` does. An existing row is never edited: when the
    named row sits at another level, None comes back and no band is made for it.
    """
    CheckOutcome = apps.get_model("arxii", "CheckOutcome")
    outcome, _ = CheckOutcome.objects.get_or_create(
        name=OUTCOME_NAME_AT_LEVEL[success_level], defaults={"success_level": success_level}
    )
    if outcome.success_level != success_level:
        return None
    return outcome


def _check_type(apps, name):
    """The willpower (1.0) plus composure (0.5) check type called *name*.

    Traits are attached only to a check type made here; an authored one is used as it is.
    A trait that does not exist is skipped, never created: the "Required content" probes
    report a check type left without its traits.
    """
    CheckCategory = apps.get_model("arxii", "CheckCategory")
    CheckType = apps.get_model("arxii", "CheckType")
    CheckTypeTrait = apps.get_model("arxii", "CheckTypeTrait")
    Trait = apps.get_model("arxii", "Trait")

    check_type = CheckType.objects.filter(name=name).first()
    if check_type is not None:
        return check_type
    category, _ = CheckCategory.objects.get_or_create(
        name="Species",
        defaults={"description": "", "display_order": 97},
    )
    check_type = CheckType.objects.create(name=name, category=category, description="")
    for trait_name, weight in (("willpower", "1.00"), ("composure", "0.50")):
        trait = Trait.objects.filter(name=trait_name).first()
        if trait is not None:
            CheckTypeTrait.objects.create(check_type=check_type, trait=trait, weight=weight)
    return check_type


def _berserk_compulsion(apps):
    """Berserk's compulsion, unless it has one. Returns the Berserk template, or None."""
    FuryConfig = apps.get_model("arxii", "FuryConfig")
    Compulsion = apps.get_model("arxii", "Compulsion")
    ForbiddenAction = apps.get_model("arxii", "CompulsionForbiddenAction")
    ResistBand = apps.get_model("arxii", "CompulsionResistBand")

    config = FuryConfig.objects.filter(berserk_condition__isnull=False).first()
    if config is None:
        return None
    if Compulsion.objects.filter(condition_id=config.berserk_condition_id).exists():
        return config.berserk_condition
    compulsion = Compulsion.objects.create(
        condition_id=config.berserk_condition_id,
        wants="attack_opponent",
        check_type=_check_type(apps, "Resist compulsion"),
        base_difficulty=25,
        difficulty_per_severity=2,
        retry_wait_minutes=5,
    )
    for action, extra in (("flee", 5), ("parley", 5), ("leave", 10), ("revert_form", 10)):
        ForbiddenAction.objects.create(compulsion=compulsion, action=action, extra_difficulty=extra)
    for level, result, penalty, control in (
        (2, "acts_freely", 0, 0),
        (1, "acts_freely", 0, 0),
        (0, "acts_strained", 4, -2),
        (-1, "compulsion_acts", 4, -2),
        (-2, "compulsion_acts", 4, -4),
    ):
        outcome = _outcome(apps, level)
        if outcome is None:
            continue
        ResistBand.objects.create(
            compulsion=compulsion,
            outcome=outcome,
            result=result,
            action_penalty=penalty,
            control_change=control,
        )
    return config.berserk_condition


def _moon_block(apps, berserk):
    """Lycan blood, its bearers and the moon trigger, for a drawback with no moon trigger."""
    SpeciesGiftGrant = apps.get_model("arxii", "SpeciesGiftGrant")
    ControlLossTrigger = apps.get_model("arxii", "ControlLossTrigger")
    ConditionCategory = apps.get_model("arxii", "ConditionCategory")
    ConditionTemplate = apps.get_model("arxii", "ConditionTemplate")
    CharacterDistinction = apps.get_model("arxii", "CharacterDistinction")
    ConditionInstance = apps.get_model("arxii", "ConditionInstance")

    grant = SpeciesGiftGrant.objects.filter(gift__name=LYCAN_GIFT_NAME).first()
    if grant is None or berserk is None:
        return
    if grant.drawback_condition_id is not None:
        # A drawback already set: only a missing trigger is made, on that drawback.
        blood = grant.drawback_condition
        if not blood.control_loss_triggers.filter(fires_on="moon_pull").exists():
            _moon_trigger(apps, blood, grant, berserk)
        return
    if ControlLossTrigger.objects.filter(fires_on="moon_pull").exists():
        return
    category, _ = ConditionCategory.objects.get_or_create(
        name="Instinct",
        defaults={"description": "", "is_negative": False},
    )
    # A nameplate with no prose. It is made here, so it is permanent and has no stages.
    blood, created = ConditionTemplate.objects.get_or_create(
        name="Lycan blood",
        defaults={
            "category": category,
            "default_duration_type": "permanent",
            "is_stackable": False,
            "can_be_dispelled": False,
        },
    )
    grant.drawback_condition = blood
    grant.save(update_fields=["drawback_condition"])
    if created:
        # A character sheet shares its pk with the character's ObjectDB row.
        sheet_ids = set(
            CharacterDistinction.objects.filter(
                distinction__tags__slug=MOON_BOUND_TAG_SLUG
            ).values_list("character_id", flat=True)
        )
        ConditionInstance.objects.bulk_create(
            [ConditionInstance(target_id=pk, condition=blood) for pk in sorted(sheet_ids)]
        )
    if not blood.control_loss_triggers.filter(fires_on="moon_pull").exists():
        _moon_trigger(apps, blood, grant, berserk)


def _moon_check_type(apps):
    """An existing "moon_control" check (an earlier seed's name), else "Hold against the moon".

    Never a second moon check beside an existing one, and no row is renamed.
    """
    CheckType = apps.get_model("arxii", "CheckType")

    legacy = CheckType.objects.filter(name="moon_control").first()
    if legacy is not None:
        return legacy
    return _check_type(apps, "Hold against the moon")


def _moon_trigger(apps, blood, grant, berserk):
    """The moon-pull trigger on *blood* and its bands, rolled on "Hold against the moon"."""
    ControlLossTrigger = apps.get_model("arxii", "ControlLossTrigger")
    ControlLossBand = apps.get_model("arxii", "ControlLossBand")

    trigger = ControlLossTrigger.objects.create(
        vulnerability=blood,
        fires_on="moon_pull",
        min_moon_pull=6,
        check_type=_moon_check_type(apps),
        base_difficulty=20,
        difficulty_per_pull=5,
        relief_per_level=10,
        relief_gift_id=grant.gift_id,
        relief_per_thread_level=5,
        relief_cap=30,
        exempt_from_level=6,
        impaired_willpower_drop=10,
    )
    for level in (2, 1, 0, -1, -2):
        outcome = _outcome(apps, level)
        if outcome is None:
            continue
        extra = (
            {"applies": berserk, "severity": 3, "duration_rounds": 3, "forces_form": True}
            if level < 0
            else {}
        )
        ControlLossBand.objects.create(trigger=trigger, outcome=outcome, **extra)


def seed_control_loss_content(apps, schema_editor):
    _moon_block(apps, _berserk_compulsion(apps))


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0346_control_loss_compulsion"),
    ]

    operations = [
        migrations.RunPython(seed_control_loss_content, migrations.RunPython.noop),
    ]
