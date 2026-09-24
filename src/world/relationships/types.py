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
    """One row of the tie page's stream: a journal entry or a scene both took part in.

    ``is_capstone`` is unconditional (#3957 review): even a THIRD_PARTY may see that an
    entry marked a tier capstone, just not which tier — ``capstone_tier`` is null for
    that audience so the number itself never leaks through the stream.
    """

    kind: str  # "entry" | "scene"
    id: int
    title: str
    author_id: int | None
    author_name: str
    body: str
    is_public: bool
    is_capstone: bool
    capstone_tier: int | None
    created_at: str
    ic_timestamp: str | None
