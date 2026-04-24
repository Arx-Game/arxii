"""Return types for Spec C gain services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


@dataclass(frozen=True)
class SettlementResult:
    """Result of settling one endorser's weekly pot.

    Carries the CharacterSheet instance (not a PK) per user's dataclass-carry-
    model-instances preference — callers want the instance for audit display.
    """

    endorser_sheet: CharacterSheet
    endorsements_settled: int
    total_granted: int


@dataclass(frozen=True)
class ResonanceDailyTickSummary:
    residence_grants_issued: int = 0
    outfit_grants_issued: int = 0
    sheets_processed: int = 0


@dataclass(frozen=True)
class ResonanceWeeklySettlementSummary:
    endorsers_settled: int = 0
    total_endorsements_settled: int = 0
    total_granted: int = 0
