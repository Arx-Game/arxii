"""Type definitions for the GM system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.gm.models import (
        CheckTypeSituationFit,
        ConsequencePoolGuide,
        GMLevelChange,
        SituationDifficultyGuide,
        SituationKind,
    )
    from world.magic.models import Technique
    from world.mechanics.models import ChallengeTemplate, SituationTemplate
    from world.scenes.models import Scene
    from world.stories.models import StakeOutcome


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


@dataclass(frozen=True)
class KindResult:
    """One situation kind with everything the catalog says about it (#3564).

    ``difficulty_guide`` is the guide for the requested risk (None when no
    risk was given or the kind has no guide for it); ``all_guides`` is every
    guide, ordered by risk, so a browse with no risk still shows the ladder.
    """

    kind: SituationKind
    check_fits: list[CheckTypeSituationFit]
    difficulty_guide: SituationDifficultyGuide | None
    all_guides: list[SituationDifficultyGuide]
    pool_guides: list[ConsequencePoolGuide]


@dataclass(frozen=True)
class DiscoveryResult:
    """What ``find_situations`` found: the shape both the telnet action and
    ``GET /api/gm/discovery/`` render (#3564)."""

    templates: list[SituationTemplate]
    challenges: list[ChallengeTemplate]
    kinds: list[KindResult]


@dataclass(frozen=True)
class NarratableEvent:
    """A mechanical event a GM may narrate (#4101). Text is already resolved."""

    kind: str
    scene: Scene | None
    character_sheet: CharacterSheet | None
    room_text: str = ""
    private_text: str = ""
    prepared_for_character: bool = False
    technique: Technique | None = None
    stake_outcome: StakeOutcome | None = None


@dataclass(frozen=True)
class GMAttention:
    """Everything waiting on one GM, as counts (#4188).

    One answer for the header's GMing badge and the Dashboard's "Waiting on
    you" strip, so the two can never disagree (ADR-4188). Each count is scoped
    to the account that asked; ``total`` is their sum.
    """

    story_offers: int
    crossover_invites: int
    sheet_update_requests: int
    claims_to_approve: int
    my_claims: int
    session_requests: int

    @property
    def total(self) -> int:
        return (
            self.story_offers
            + self.crossover_invites
            + self.sheet_update_requests
            + self.claims_to_approve
            + self.my_claims
            + self.session_requests
        )
