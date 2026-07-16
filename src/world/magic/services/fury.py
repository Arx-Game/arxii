"""Fury lever resolution service.

Pure computation layer: provocation cap (bond-derived ceiling on tier depth),
tier clamping, and control-retention outcome assembly. The caller (Task 6)
performs the control-retention check and passes the CheckResult in; this
module stays free of I/O side-effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from evennia.objects.models import ObjectDB

from world.character_sheets.models import CharacterSheet
from world.magic.models import FuryConfig, FuryTier
from world.relationships.helpers import get_relationship_tier

if TYPE_CHECKING:
    from world.checks.models import CheckType


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


def get_fury_config() -> FuryConfig:
    """Public singleton accessor."""
    return _config()


def _ensure_fury_check_type(trait_name: str) -> CheckType:
    """Return the CheckType for a fury control-retention check keyed on trait_name.

    Lazy-creates the CheckType + CheckCategory if not present (mirrors
    fatigue._ensure_endurance_check_type). Requires the trait fixture row to exist.
    """
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    check_category, _ = CheckCategory.objects.get_or_create(
        name="Fury",
        defaults={"description": "Fury control-retention checks", "display_order": 98},
    )
    check_type_name = f"fury_control_retention_{trait_name}"
    check_type, created = CheckType.objects.get_or_create(
        name=check_type_name,
        category=check_category,
        defaults={"description": f"Control-retention check for fury ({trait_name})"},
    )
    if created:
        trait = Trait.objects.filter(name=trait_name, trait_type=TraitType.STAT).first()
        if trait is not None:
            CheckTypeTrait.objects.create(check_type=check_type, trait=trait, weight=1.0)
    return check_type


def resolve_fury(*, character, tier, anchor, check_result) -> FuryResolution:
    """Assemble a FuryResolution from the given parameters.

    Args:
        character: The ObjectDB character invoking fury.
        tier: The FuryTier the player declared.
        anchor: The CharacterSheet fury anchor (nullable FK — None means unavailable).
        check_result: A CheckResult-like object with ``success_level`` int;
            None is treated as success_level=0.

    The declared tier is always clamped to the bond-derived provocation cap.
    ``provocation_cap`` returns 0 when character or anchor is None, so a null
    anchor naturally yields FuryResolution(None, 0, 0, 0) without special-casing.
    """
    cap = provocation_cap(character, anchor)
    realized = clamp_tier(tier, cap)
    if realized is None:
        return FuryResolution(None, 0, 0, 0)
    cfg = _config()
    # Mirrors StrainConfig singleton read in world/fatigue/services.py.
    bonus = realized.intensity_bonus * (100 + cfg.bonus_scale_per_cap_point * cap) // 100
    grade = check_result.success_level if check_result is not None else 0
    berserk = 0 if grade >= realized.lucid_grade_floor else realized.berserk_severity
    return FuryResolution(realized, realized.control_penalty, bonus, berserk)


def run_fury_for_action(
    *,
    character: ObjectDB,
    fury_commitment: FuryTier | None,
    fury_anchor: CharacterSheet | None,
    source_technique=None,
) -> FuryResolution | None:
    """Run the control-retention check, assemble the FuryResolution, apply Berserk.

    Single orchestration seam shared by the enhanced-action, cast, and plain-action
    resolution paths so the check/resolve/apply-Berserk sequence lives in one place.

    Returns None when no fury was declared (``fury_commitment is None``); otherwise
    returns the FuryResolution. The caller is responsible for feeding
    ``control_penalty`` / ``intensity_bonus`` into ``use_technique`` (technique paths)
    and recording ``realized_tier`` as the audit value.

    Args:
        character: The ObjectDB character invoking fury.
        fury_commitment: The declared FuryTier, or None for no fury.
        fury_anchor: The CharacterSheet the rage answers to (bond caps the tier).
        source_technique: Optional Technique to credit as the Berserk source.
    """
    if fury_commitment is None:
        return None

    from world.checks.services import perform_check  # noqa: PLC0415

    cfg = _config()
    check_type = _ensure_fury_check_type(cfg.check_trait)
    ease = provocation_ease(character, fury_anchor)
    target_diff = max(fury_commitment.base_check_difficulty - ease, 0)
    check = perform_check(character, check_type, target_difficulty=target_diff)
    fury_res = resolve_fury(
        character=character, tier=fury_commitment, anchor=fury_anchor, check_result=check
    )

    if fury_res.berserk_severity > 0:
        from world.conditions.models import ConditionTemplate  # noqa: PLC0415
        from world.conditions.services import apply_condition  # noqa: PLC0415

        apply_condition(
            character,
            ConditionTemplate.get_by_name("Berserk"),
            severity=fury_res.berserk_severity,
            duration_rounds=cfg.default_berserk_duration_rounds,
            source_character=character,
            source_technique=source_technique,
        )

    return fury_res
