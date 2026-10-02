"""Value objects for resolved prepared Audere text (#4101).

Resolution composes three layers (character, then patron variant, then tier) —
see ``world.magic.services.prepared_text``. These dataclasses are the resolved
shape handed back to the caller; they carry no identity of their own.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrossingText:
    """Resolved text for one Audere Majora crossing."""

    vision: str
    manifestation: str
    deed_title: str  # "" = compose the generic title
    prepared: bool  # True iff the VISION specifically came from prepared text (#4101 fix round 1)


@dataclass(frozen=True)
class SurgeText:
    """Resolved text for one Audere surge."""

    text: str  # still carries {name}; the caller substitutes
    prepared: bool
