"""Redirect detonation content seed (#2210).

Idempotently seeds one example volatile ``Property`` — "Volatile (Powder)" — and
its authored ``PropertyDetonation`` sidecar carrying a small consequence pool.
An object carrying an ``ObjectProperty`` for this Property is "volatile":
declaring a redirect (see ``world.combat.services.declare_interpose`` /
``_try_technique_interpose``) into it fires the pool against every combatant at
the object's Position, then deletes the triggering ``ObjectProperty`` row — a
one-shot detonation.

Mirrors ``world.combat.interpose_content.ensure_interpose_content``'s idiom:
self-contained, ``get_or_create`` throughout, safe to call repeatedly. Doubles
as integration-test setup and staff seed data.
"""

from world.checks.constants import EffectType
from world.checks.models import Consequence, ConsequenceEffect
from world.conditions.models import DamageType
from world.mechanics.models import Property, PropertyCategory, PropertyDetonation
from world.traits.models import CheckOutcome

VOLATILE_POWDER_PROPERTY_NAME: str = "Volatile (Powder)"
_DETONATION_POOL_NAME: str = "Volatile Powder Detonation"
_DETONATION_DAMAGE_AMOUNT: int = 15


def ensure_redirect_content() -> Property:
    """Idempotently seed the "Volatile (Powder)" example volatile Property.

    Seeds a "Hazard" ``PropertyCategory``, the Property itself, a
    deterministic-fire ``ConsequencePool`` carrying one DEAL_DAMAGE
    ``Consequence``, and the ``PropertyDetonation`` sidecar linking them.
    Returns the seeded Property (the caller attaches an ``ObjectProperty`` to
    make a specific object volatile).
    """
    from actions.models.consequence_pools import (  # noqa: PLC0415
        ConsequencePool,
        ConsequencePoolEntry,
    )

    category, _ = PropertyCategory.objects.get_or_create(
        name="Hazard",
        defaults={"description": "Properties describing environmental hazards."},
    )
    volatile_property, _ = Property.objects.get_or_create(
        name=VOLATILE_POWDER_PROPERTY_NAME,
        defaults={
            "description": (
                "A cache of alchemical powder, primed to detonate if struck or ignited."
            ),
            "category": category,
        },
    )

    outcome, _ = CheckOutcome.objects.get_or_create(
        name="Detonation",
        defaults={
            "description": "Deterministic environmental firing — no roll involved.",
            "success_level": 0,
        },
    )
    consequence, _ = Consequence.objects.get_or_create(
        outcome_tier=outcome,
        label="Powder detonation",
        defaults={
            "mechanical_description": "The powder cache goes up, scattering blast damage.",
            "weight": 1,
            "character_loss": False,
        },
    )
    damage_type, _ = DamageType.objects.get_or_create(
        name="Fire",
        defaults={"description": "Heat and flame damage."},
    )
    ConsequenceEffect.objects.get_or_create(
        consequence=consequence,
        effect_type=EffectType.DEAL_DAMAGE,
        defaults={
            "damage_amount": _DETONATION_DAMAGE_AMOUNT,
            "damage_type": damage_type,
        },
    )

    pool, _ = ConsequencePool.objects.get_or_create(
        name=_DETONATION_POOL_NAME,
        defaults={
            "description": "Fired once against every combatant at a detonating object's position.",
        },
    )
    ConsequencePoolEntry.objects.get_or_create(pool=pool, consequence=consequence)

    PropertyDetonation.objects.get_or_create(
        property=volatile_property,
        defaults={
            "consequence_pool": pool,
            "description": "A small alchemical blast — the framework-proving example detonation.",
        },
    )

    return volatile_property
