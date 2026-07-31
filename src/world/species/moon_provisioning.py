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

from world.species.moon_constants import WOLFS_FURY_GIFT_NAME

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.forms.models import AlternateSelf

logger = logging.getLogger(__name__)

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
        defaults={"display_name": WOLFS_FURY_GIFT_NAME},
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
    """Thread level on the species gift (0 when unwoven)."""
    from world.magic.models import Thread  # noqa: PLC0415

    thread = Thread.objects.filter(
        owner=sheet,
        target_gift__name=WOLFS_FURY_GIFT_NAME,
        retired_at__isnull=True,
    ).first()
    return thread.level if thread is not None else 0
