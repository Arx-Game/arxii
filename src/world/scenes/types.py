"""TypedDict definitions for scene interaction payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from actions.types import PendingActionResolution
from world.magic.types import TechniqueUseResult


class PersonaPayload(TypedDict):
    """Persona data embedded in interaction payloads."""

    id: int
    name: str
    thumbnail_url: str


class InteractionPayload(TypedDict):
    """Structured interaction payload for WebSocket delivery."""

    id: int
    persona: PersonaPayload
    content: str
    mode: str
    timestamp: str
    scene_id: int | None
    place_id: int | None
    place_name: str | None
    receiver_persona_ids: list[int]
    target_persona_ids: list[int]


class ReactionAggregation(TypedDict):
    """Aggregated emoji reaction with current-user flag."""

    emoji: str
    count: int
    reacted: bool


@dataclass
class EnhancedSceneActionResult:
    """Combined result of a social action, optionally technique-enhanced."""

    action_resolution: PendingActionResolution
    action_key: str
    technique_result: TechniqueUseResult | None = None
