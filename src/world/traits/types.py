"""
Type definitions for the traits system.

Contains dataclasses, TypedDicts, and other type declarations that need to be
shared across modules without creating circular import issues.
"""

from dataclasses import dataclass, field


@dataclass
class StatDisplayInfo:
    """Display-formatted stat information for API/UI responses."""

    value: int
    display: int
    modifiers: list = field(default_factory=list)
