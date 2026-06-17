"""Fury lever resolution service.

Pure computation layer: provocation cap (bond-derived ceiling on tier depth),
tier clamping, and control-retention outcome assembly. The caller (Task 6)
performs the control-retention check and passes the CheckResult in; this
module stays free of I/O side-effects.
"""

from __future__ import annotations

from dataclasses import dataclass

from evennia.objects.models import ObjectDB

from world.character_sheets.models import CharacterSheet
from world.magic.models import FuryConfig, FuryTier
from world.relationships.helpers import get_relationship_tier


@dataclass(frozen=True)
class FuryResolution:
    """Outcome of a fury escalation attempt."""

    realized_tier: FuryTier | None
    control_penalty: int
    intensity_bonus: int
    berserk_severity: int


def _config() -> FuryConfig:
    return FuryConfig.objects.filter(pk=1).first() or FuryConfig()


def provocation_cap(character: ObjectDB | None, anchor: CharacterSheet | None) -> int:
    """Bond-derived ceiling on fury depth.

    Returns 0 when fury is unavailable (missing character or anchor, or the
    anchor sheet has no linked ObjectDB character).
    """
    if character is None or anchor is None:
        return 0
    anchor_char = anchor.character
    if anchor_char is None:
        return 0
    bond = get_relationship_tier(character, anchor_char)
    per = max(_config().provocation_cap_per_tier, 1)
    return bond // per if per else bond


def provocation_ease(character: ObjectDB | None, anchor: CharacterSheet | None) -> int:
    """Check-difficulty reduction from the bond (cap * cap_ease_per_point)."""
    return provocation_cap(character, anchor) * _config().cap_ease_per_point


def clamp_tier(declared_tier: FuryTier, cap: int) -> FuryTier | None:
    """Deepest authored tier with depth <= cap.

    Returns None if cap is 0 or below the shallowest available tier.
    """
    if cap <= 0:
        return None
    if declared_tier.depth <= cap:
        return declared_tier
    return FuryTier.objects.filter(depth__lte=cap).order_by("-depth").first()


def resolve_fury(*, character, tier, anchor, check_result) -> FuryResolution:
    """Assemble a FuryResolution from the given parameters.

    Args:
        character: The ObjectDB character invoking fury (may be None in tests).
        tier: The FuryTier the player declared.
        anchor: The CharacterSheet fury anchor (may be None in tests).
        check_result: A CheckResult-like object with ``success_level`` int;
            None is treated as success_level=0.

    When character and anchor are both provided, the declared tier is clamped
    to the bond-derived provocation cap. When either is None (e.g. in unit
    tests) the tier is used as-is without clamping.
    """
    if character is not None and anchor is not None:
        cap = provocation_cap(character, anchor)
        realized = clamp_tier(tier, cap) if cap else None
        if realized is None:
            return FuryResolution(None, 0, 0, 0)
    else:
        realized = tier
        cap = 0
    cfg = _config()
    bonus = realized.intensity_bonus * (100 + cfg.bonus_scale_per_cap_point * cap) // 100
    grade = getattr(check_result, "success_level", 0)  # noqa: GETATTR_LITERAL
    berserk = 0 if grade >= realized.lucid_grade_floor else realized.berserk_severity
    return FuryResolution(realized, realized.control_penalty, bonus, berserk)
