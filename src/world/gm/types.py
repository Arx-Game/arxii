"""Type definitions for the GM system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.gm.models import GMLevelChange


@dataclass(frozen=True)
class CategoryFeedback:
    """One trust category's aggregated feedback ratings for a GM."""

    category_name: str
    average_rating: float
    rating_count: int


@dataclass(frozen=True)
class GMEvidenceSummary:
    """Read model backing the GM trust-ladder evidence view.

    Aggregates a GM's track record (stories run, beats completed by risk
    tier, feedback by trust category) plus the audit trail of level
    changes, for staff reviewing a promotion/demotion decision.
    """

    profile_id: int
    level: str
    approved_at: datetime
    last_active_at: datetime | None
    stories_running: int
    beats_completed_by_risk: dict[str, int]
    feedback_by_category: list[CategoryFeedback]
    level_changes: list[GMLevelChange]
