"""Lycan battle-form provisioning (#2845): the shape The Wolf's Fury wears.

The battle form rides the built alternate-self machinery whole: a
``CharacterForm`` (ALTERNATE), a ``FormCombatProfile`` stat suite, and an
``AlternateSelf`` binding them — all per-character rows, provisioned lazily
and idempotently. The moon reconcile calls this before a forced shift, so a
moon-bound character self-heals a missing battle form the first time the moon
takes them; a CG-time provisioning hook can call the same seam later.

Stat magnitudes are a PLACEHOLDER author pass (sequence with TehomCD's
species-gift content work). ``tuning_value`` bakes gift-thread mastery into
the suite (10 = baseline; each thread level adds), refreshed on every ensure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.conditions.models import ConditionTemplate, ControlLossTrigger
    from world.forms.models import AlternateSelf

logger = logging.getLogger(__name__)

LYCAN_BLOOD_NAME = "Lycan blood"
# Seed-only lookup literals: the lycan species and its gift are found by name once, when
# the seed wires the grant. Runtime code finds the vulnerability through conditions.
SEED_LYCAN_SPECIES_NAME = "Lycan"
SEED_LYCAN_GIFT_NAME = "The Wolf's Fury"
# Seed-only: the Moon-Bound distinction and its tag, stamped on the lycan grant at CG.
SEED_MOON_BOUND_TAG = "moon-bound"
SEED_MOON_BOUND_SLUG = "moon-bound"
# Config row named by a code literal (ADR-0171), registered in config_prerequisites. The
# literal is the name players read on the roll line; it only names a row this code
# creates. Runtime finds the check through ``ControlLossTrigger.check_type``, never by name,
# and no existing row is ever renamed.
MOON_CONTROL_CHECK_NAME = "Hold against the moon"
# The name an earlier seed gave the same check (#2845). A database that already has it
# keeps using it, so no second moon check is ever made beside it (#4802).
LEGACY_MOON_CONTROL_CHECK_NAME = "moon_control"

BATTLE_FORM_NAME = "Battle Form"
# PLACEHOLDER stat suite: (stat trait name, modifier value).
BATTLE_FORM_STAT_SUITE = (
    ("strength", 2),
    ("agility", 2),
    ("stamina", 2),
)
TUNING_BASELINE = 10
TUNING_PER_THREAD_LEVEL = 1


def ensure_lycan_battle_form(sheet: CharacterSheet) -> AlternateSelf:
    """Idempotently provision *sheet*'s battle form; refresh thread tuning."""
    from world.forms.models import (  # noqa: PLC0415
        AlternateSelf,
        CharacterForm,
        FormCombatProfile,
        FormCombatProfileEffect,
        FormType,
    )

    form, _created = CharacterForm.objects.get_or_create(
        character=sheet,
        name=BATTLE_FORM_NAME,
        form_type=FormType.ALTERNATE,
    )
    profile, _created = FormCombatProfile.objects.get_or_create(
        form=form,
        defaults={"display_name": SEED_LYCAN_GIFT_NAME},
    )
    for trait_name, value in BATTLE_FORM_STAT_SUITE:
        target = _stat_modifier_target(trait_name)
        if target is None:
            continue
        FormCombatProfileEffect.objects.get_or_create(
            profile=profile,
            target=target,
            defaults={"value": value},
        )
    alt, _created = AlternateSelf.objects.get_or_create(
        character=sheet,
        form=form,
        defaults={
            "combat_profile": profile,
            "display_name": BATTLE_FORM_NAME,
        },
    )
    tuning = TUNING_BASELINE + _gift_thread_level(sheet) * TUNING_PER_THREAD_LEVEL
    if alt.tuning_value != tuning or alt.combat_profile_id != profile.pk:
        alt.tuning_value = tuning
        alt.combat_profile = profile
        alt.save(update_fields=["tuning_value", "combat_profile"])
    return alt


def _stat_modifier_target(trait_name: str):
    """The stat-category ModifierTarget for *trait_name*, get-or-created.

    Tolerant of a missing Trait row (skip, don't invent) — stat Traits are
    content-fixture rows, mirroring fury's check-type pattern.
    """
    from world.mechanics.models import ModifierCategory, ModifierTarget  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    trait = Trait.objects.filter(name=trait_name, trait_type=TraitType.STAT).first()
    if trait is None:
        return None
    category, _created = ModifierCategory.objects.get_or_create(
        name="stat",
        defaults={"description": "Stat modifiers."},
    )
    target, _created = ModifierTarget.objects.get_or_create(
        name=trait_name,
        category=category,
        defaults={"target_trait": trait},
    )
    if target.target_trait_id is None:
        target.target_trait = trait
        target.save(update_fields=["target_trait"])
    return target


def _gift_thread_level(sheet: CharacterSheet) -> int:
    """Thread level on the gift the sheet's moon trigger gives relief for (0 when unwoven)."""
    from world.conditions.constants import ControlLossFiresOn  # noqa: PLC0415
    from world.conditions.models import ControlLossTrigger  # noqa: PLC0415
    from world.magic.models import Thread  # noqa: PLC0415

    trigger = (
        ControlLossTrigger.objects.filter(
            fires_on=ControlLossFiresOn.MOON_PULL,
            relief_gift__isnull=False,
            vulnerability__conditioninstance__target_id=sheet.pk,
        )
        .order_by("pk")
        .first()
    )
    if trigger is None:
        return 0
    thread = (
        Thread.objects.filter(
            owner=sheet, target_gift_id=trigger.relief_gift_id, retired_at__isnull=True
        )
        .order_by("pk")
        .first()
    )
    return thread.level if thread is not None else 0


def ensure_lycan_blood_condition() -> ConditionTemplate:
    """Idempotently seed the permanent "Lycan blood" vulnerability condition (#4802).

    It sits in a category that does not alter behavior (a vulnerability is carried, it
    does not drive the bearer), and is the lycan grant's ``drawback_condition``.
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415

    category, _ = ConditionCategory.objects.get_or_create(
        name="Instinct",
        defaults={"description": "", "is_negative": False},
    )
    template, _ = ConditionTemplate.objects.get_or_create(
        name=LYCAN_BLOOD_NAME,
        defaults={
            "category": category,
            "default_duration_type": DurationType.PERMANENT,
            "is_stackable": False,
            "can_be_dispelled": False,
        },
    )
    return template


def ensure_moon_control_loss_trigger() -> ControlLossTrigger | None:
    """Idempotently seed the moon's control-loss trigger on Lycan blood (#4802).

    The trigger hangs on the lycan grant's ``drawback_condition``. Returns None, writing
    nothing, until the Berserk designation (``FuryConfig``) exists and the grant has a
    drawback. A trigger that already exists is returned untouched, bands and all.
    """
    from world.conditions.berserk_content import outcome_at_level  # noqa: PLC0415
    from world.conditions.constants import ControlLossFiresOn  # noqa: PLC0415
    from world.conditions.models import ControlLossBand, ControlLossTrigger  # noqa: PLC0415
    from world.magic.models import FuryConfig  # noqa: PLC0415
    from world.species.models import SpeciesGiftGrant  # noqa: PLC0415

    config, _ = FuryConfig.objects.get_or_create(pk=1)
    berserk = config.berserk_condition
    grant = (
        SpeciesGiftGrant.objects.filter(
            species__name=SEED_LYCAN_SPECIES_NAME, gift__name=SEED_LYCAN_GIFT_NAME
        )
        .order_by("pk")
        .first()
    )
    if berserk is None or grant is None or grant.drawback_condition is None:
        return None
    trigger, created = ControlLossTrigger.objects.get_or_create(
        vulnerability=grant.drawback_condition,
        fires_on=ControlLossFiresOn.MOON_PULL,
        defaults={
            "min_moon_pull": 6,
            "check_type": _ensure_moon_control_check_type(),
            "base_difficulty": 20,
            "difficulty_per_pull": 5,
            "relief_per_level": 10,
            "relief_gift": grant.gift,
            "relief_per_thread_level": 5,
            "relief_cap": 30,
            "exempt_from_level": 6,
            "impaired_willpower_drop": 10,
        },
    )
    if not created:
        return trigger
    # (success_level, applies Berserk): Partial Success and up give nothing.
    for level, applies in ((2, False), (1, False), (0, False), (-1, True), (-2, True)):
        ControlLossBand.objects.create(
            trigger=trigger,
            outcome=outcome_at_level(level),
            **(
                {"applies": berserk, "severity": 3, "duration_rounds": 3, "forces_form": True}
                if applies
                else {}
            ),
        )
    return trigger


def _ensure_moon_control_check_type() -> CheckType:
    """The moon's check type: an existing "moon_control" row, else "Hold against the moon".

    A database an earlier seed gave "moon_control" keeps that row as it is (never renamed,
    never a second moon check beside it); only when it is absent is the willpower +
    composure check made, or reused, under its player-facing name. Config row named by a
    code literal (ADR-0171), also registered in ``world.seeds.config_prerequisites`` so it
    exists after a press.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.conditions.berserk_content import ensure_willpower_check_type  # noqa: PLC0415

    try:
        return CheckType.objects.get(name=LEGACY_MOON_CONTROL_CHECK_NAME)
    except CheckType.DoesNotExist:
        return ensure_willpower_check_type(MOON_CONTROL_CHECK_NAME)
