"""Idempotent seed for Companion catalog content (#672).

Mirrors world/conditions/charm_content.py's ensure_charm_content: get_or_create
the Beastlord Gift, its granting Resonance, beast CompanionArchetype rows, the
"Bind Attempt" CheckType, and the ThreadPullEffect capacity-grant rows.
Exercised from tests only in this pass — no build_schema.py wiring yet, since
this is the only concrete consumer shipping in this PR (#672 spec, Decision #14).
"""

from __future__ import annotations

from world.checks.models import CheckCategory, CheckType
from world.companions.constants import CompanionDomain
from world.companions.models import CompanionArchetype
from world.magic.constants import EffectKind, GiftKind, TargetKind
from world.magic.models.affinity import Affinity, Resonance
from world.magic.models.gifts import Gift
from world.magic.models.threads import ThreadPullEffect

BEASTLORD_GIFT_NAME = "Beastlord"
BIND_ATTEMPT_CHECK_NAME = "Bind Attempt"

_BEAST_ARCHETYPES = [
    ("Hawk", "A keen-eyed aerial scout.", 20, 5),
    ("Wolf", "A loyal pack-hunter.", 30, 10),
    ("Direwolf", "A massive, fearsome hunter.", 50, 20),
]

_CAPACITY_TIERS = [
    (10, 10),
    (20, 20),
    (30, 35),
]


def ensure_companion_content() -> Gift:
    """Idempotently seed Beastlord gift + beast archetypes + bind check + capacity rows.

    Returns the Beastlord Gift row (callers granting it to a character need it).
    """
    affinity, _ = Affinity.objects.get_or_create(
        name="Primal",
        defaults={"description": "The wild, untamed source of magical power."},
    )
    resonance, _ = Resonance.objects.get_or_create(
        name="Wild Bond",
        defaults={
            "description": "The resonance of steadfast beast companionship.",
            "affinity": affinity,
        },
    )
    gift, _ = Gift.objects.get_or_create(
        name=BEASTLORD_GIFT_NAME,
        defaults={
            "description": "Bind a wild beast as a steadfast companion.",
            "kind": GiftKind.MINOR,
        },
    )
    gift.resonances.add(resonance)

    category, _ = CheckCategory.objects.get_or_create(
        name="Companion Binding",
        defaults={"display_order": 0},
    )
    CheckType.objects.get_or_create(
        name=BIND_ATTEMPT_CHECK_NAME,
        category=category,
        defaults={
            "description": "Attempt to bind a wild beast as a companion.",
            "is_active": True,
            "display_order": 0,
        },
    )

    for name, description, bind_difficulty, capacity_cost in _BEAST_ARCHETYPES:
        CompanionArchetype.objects.get_or_create(
            name=name,
            defaults={
                "domain": CompanionDomain.BEAST,
                "description": description,
                "bind_difficulty": bind_difficulty,
                "capacity_cost": capacity_cost,
            },
        )

    for min_thread_level, flat_bonus_amount in _CAPACITY_TIERS:
        ThreadPullEffect.objects.get_or_create(
            target_kind=TargetKind.GIFT,
            resonance=resonance,
            tier=0,
            min_thread_level=min_thread_level,
            target_gift=gift,
            defaults={
                "effect_kind": EffectKind.FLAT_BONUS,
                "flat_bonus_amount": flat_bonus_amount,
            },
        )

    return gift
