"""Types for the staff inbox aggregator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class InboxItem:
    """A single item in the staff inbox.

    Represents one row from any source model (PlayerFeedback, BugReport,
    PlayerReport, RosterApplication, etc.) in a unified shape for the
    inbox display.
    """

    source_type: str  # one of SubmissionCategory values
    source_pk: int
    title: str
    reporter_summary: str
    created_at: datetime
    status: str
    detail_url: str
