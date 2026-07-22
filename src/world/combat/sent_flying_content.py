"""Sent Flying marker content seed (#2638) — the plummet-pattern's first clone.

Idempotently seeds the content the "sent flying" consequence needs:

* a "Physical" :class:`~world.conditions.models.DamageType` (blunt impact from
  an unassisted hard landing — Sent Flying's own dedicated impact type, mirroring
  Plummeting's dedicated "Fall" DamageType, with null wound/death pools so the
  config-default survivability pools apply); and
* a simple non-expiring "Sent Flying" :class:`~world.conditions.models.ConditionTemplate`
  marker, reusing Plummeting's own "Falling" :class:`~world.conditions.models.ConditionCategory`
  (#1228) rather than authoring a new one — sent-flying and falling are the same
  is_negative airborne-hazard family, and an unanswered Sent Flying marker's
  explicit resolution may hand the victim straight into an actual Plummeting
  condition (world.combat.services._resolve_sent_flying_markers).

**Duration is PERMANENT, not a literal ROUNDS/1 "one-round marker."** The design
doc's shorthand ("1-round marker") describes the marker's INTENDED lifespan, not
its Django ``default_duration_type``: applying it with ``ROUNDS``/``1`` would let
the generic end-of-round duration countdown (``tick_round_for_targets`` inside
``resolve_round``, which runs BEFORE the sent-flying resolution pass in the same
function) auto-delete the marker before that explicit resolution code ever sees
it — the same auto-expiry race Plummeting's own docstring calls out and avoids
the same way. ``PERMANENT`` leaves ``rounds_remaining=None`` so only
``world.combat.services._resolve_sent_flying_markers`` (the unanswered-impact /
plummet-chain resolution) or an earlier mid-air catch ever removes it — a
judgment call (#2638), mirroring ``ensure_fall_content``'s own reasoning for
Plummeting almost verbatim.

The Sent Flying condition has **no** stages and **no**
``ConditionDamageOverTime`` row — impact is applied explicitly (Task 5), never
as per-round DoT.

``ensure_sent_flying_content`` mirrors
``world.areas.positioning.plummet_content.ensure_fall_content`` and is safe to
call repeatedly: every write goes through ``get_or_create``. It doubles as
integration-test setup and staff seed data.
"""

from __future__ import annotations

from world.areas.positioning.constants import FALLING_CATEGORY_NAME
from world.conditions.constants import DurationType
from world.conditions.models import ConditionCategory, ConditionTemplate, DamageType

# ---------------------------------------------------------------------------
# Identity keys
# ---------------------------------------------------------------------------

SENT_FLYING_CONDITION_NAME: str = "Sent Flying"

# Sent Flying's own dedicated hard-landing impact DamageType (#2638) — mirrors
# FALL_DAMAGE_TYPE_NAME's ("Fall") role for Plummeting. Distinct from whatever
# damage_type the triggering ThreatPoolEntry itself carries: the impact is
# generic blunt trauma from striking the ground, not a continuation of the
# attack that launched the victim.
SENT_FLYING_IMPACT_DAMAGE_TYPE_NAME: str = "Physical"


def _ensure_sent_flying_impact_damage_type() -> DamageType:
    """Idempotently seed the sent-flying hard-landing impact DamageType.

    Leaves the consequence pools null so the config-default survivability
    fallback applies (the same idiom as the fall/poison/exhaustion DamageTypes).
    """
    obj, _ = DamageType.objects.get_or_create(
        name=SENT_FLYING_IMPACT_DAMAGE_TYPE_NAME,
        defaults={
            "description": "Blunt physical trauma from a hard, unassisted landing.",
        },
    )
    return obj


def ensure_sent_flying_content() -> None:
    """Idempotently seed the Sent Flying marker content (#2638).

    Seeds the Physical impact DamageType and the Sent Flying ConditionTemplate
    as a simple non-expiring marker (no stages, no DoT), reusing Plummeting's
    own Falling ConditionCategory. Safe to call repeatedly — every write goes
    through get_or_create.
    """
    category, _ = ConditionCategory.objects.get_or_create(
        name=FALLING_CATEGORY_NAME,
        defaults={
            "description": "Uncontrolled descent through the air toward an impact.",
            "is_negative": True,
        },
    )
    _ensure_sent_flying_impact_damage_type()

    ConditionTemplate.objects.get_or_create(
        name=SENT_FLYING_CONDITION_NAME,
        defaults={
            "category": category,
            "description": (
                "A devastating blow has launched this character airborne — someone "
                "with the means may catch them before they come down hard."
            ),
            # Non-progressive, non-expiring marker: see the module docstring for
            # why PERMANENT (not a literal ROUNDS/1) is the deliberate choice.
            "has_progression": False,
            "is_stackable": False,
            "default_duration_type": DurationType.PERMANENT,
        },
    )
