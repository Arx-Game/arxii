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
from world.magic.constants import EffectKind, GiftKind, TargetKind, TechniqueFunction
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


def ensure_companion_abilities() -> None:
    """Idempotently seed sample CompanionAbility rows (#1921).

    Framework-proving seeds — one ATTACK ability per beast archetype.
    Full per-archetype content catalogs are separate content-authoring work.
    """
    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.companions.constants import CompanionAbilityKind  # noqa: PLC0415
    from world.companions.models import CompanionAbility  # noqa: PLC0415

    # Rend — a basic physical attack for the Direwolf
    direwolf = CompanionArchetype.objects.filter(name="Direwolf").first()
    if direwolf is not None:
        CompanionAbility.objects.get_or_create(
            archetype=direwolf,
            name="Rend",
            defaults={
                "ability_kind": CompanionAbilityKind.ATTACK,
                "attack_category": ActionCategory.PHYSICAL,
                "base_damage": 8,
                "description": "A savage tear with claws and teeth.",
            },
        )

    # Bite — a basic physical attack for the Wolf
    wolf = CompanionArchetype.objects.filter(name="Wolf").first()
    if wolf is not None:
        CompanionAbility.objects.get_or_create(
            archetype=wolf,
            name="Bite",
            defaults={
                "ability_kind": CompanionAbilityKind.ATTACK,
                "attack_category": ActionCategory.PHYSICAL,
                "base_damage": 5,
                "description": "A snapping bite.",
            },
        )

    # Talon — a basic physical attack for the Hawk
    hawk = CompanionArchetype.objects.filter(name="Hawk").first()
    if hawk is not None:
        CompanionAbility.objects.get_or_create(
            archetype=hawk,
            name="Talon",
            defaults={
                "ability_kind": CompanionAbilityKind.ATTACK,
                "attack_category": ActionCategory.PHYSICAL,
                "base_damage": 4,
                "description": "A raking talon strike.",
            },
        )

    # Function tags — framework-proving seeds (#2666)
    from world.companions.models import CompanionAbilityFunctionTag  # noqa: PLC0415

    # Wolf "Pin" — an ATTACK ability tagged HOLD (feeds Bulwark vow qualification).
    # Uses ATTACK kind because UTILITY requires grants_property (clean() validation);
    # the function tag is what the Sphinx reads, not the ability kind.
    wolf = CompanionArchetype.objects.filter(name="Wolf").first()
    if wolf is not None:
        pin, _ = CompanionAbility.objects.get_or_create(
            archetype=wolf,
            name="Pin",
            defaults={
                "ability_kind": CompanionAbilityKind.ATTACK,
                "attack_category": ActionCategory.PHYSICAL,
                "base_damage": 3,
                "description": "The wolf pins an enemy in place.",
            },
        )
        CompanionAbilityFunctionTag.objects.get_or_create(
            ability=pin,
            function=TechniqueFunction.HOLD,
        )

    # Hawk "Scout" — an ATTACK ability tagged PERCEPTION (feeds Pathfinder vow qualification).
    hawk = CompanionArchetype.objects.filter(name="Hawk").first()
    if hawk is not None:
        scout, _ = CompanionAbility.objects.get_or_create(
            archetype=hawk,
            name="Scout",
            defaults={
                "ability_kind": CompanionAbilityKind.ATTACK,
                "attack_category": ActionCategory.PHYSICAL,
                "base_damage": 2,
                "description": "The hawk scouts from above, spotting threats.",
            },
        )
        CompanionAbilityFunctionTag.objects.get_or_create(
            ability=scout,
            function=TechniqueFunction.PERCEPTION,
        )
