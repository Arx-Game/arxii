"""
Mechanics System Types

Dataclasses and type definitions for the mechanics service layer.
"""

from dataclasses import dataclass


@dataclass
class ModifierSourceDetail:
    """Single modifier source with calculation details."""

    source_name: str
    base_value: int
    amplification: int
    final_value: int
    is_amplifier: bool
    blocked_by_immunity: bool


@dataclass
class ModifierBreakdown:
    """Full breakdown for a modifier type."""

    modifier_type_name: str
    sources: list[ModifierSourceDetail]
    total: int
    has_immunity: bool
    negatives_blocked: int
