"""Typed read shapes for ties (#3957)."""

from __future__ import annotations

from typing import TypedDict


class DepthBreakdown(TypedDict):
    tier: int
    scenes: int
    invested: int
    their_added_depth: int
    affection: int | None
    conflict: int | None


class TieStreamItem(TypedDict):
    """One row of the tie page's stream: a journal entry or a scene both posed in."""

    kind: str  # "entry" | "scene"
    id: int
    title: str
    author_id: int | None
    author_name: str
    body: str
    is_public: bool
    capstone_tier: int | None
    created_at: str
    ic_timestamp: str | None
