"""Typed return values for the achievements app's service functions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.achievements.models import CharacterAchievement, Discovery


@dataclass(frozen=True)
class AchievementGrantResult:
    """Result of ``grant_achievement``: the earned rows plus a first-discovery signal.

    ``created_discovery`` is non-None only when THIS call created the achievement's
    one-and-only ``Discovery`` row — the "first-ever" ceremony signal. Replaces
    sniffing ``CharacterAchievement.discovery_id`` on the results now that the FK is
    gone (#3055): tenure records (``earned_by_tenure`` /
    ``Discovery.discovered_by_tenure`` / ``shared_with_tenures``) are the single
    discovery-credit mechanism.
    """

    character_achievements: list[CharacterAchievement]
    created_discovery: Discovery | None
