"""Stakes-contract adapter for Legend settlement (#3463).

``world.societies.legend_settlement`` owns the *rule* — peril floor, outcome
share, station, standouts — and deliberately knows nothing about stakes
contracts, so ``societies`` stays the reusable primitive every other system
points at (ADR-0010). This module is the half that knows about
``StakeContractActivation``: it turns a locked contract into the
system-agnostic shape that seam expects, and calls it.

Battles and missions get their own adapters for the same reason. The rule is
written once; the extraction is written per world.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.societies.legend_settlement import (
    SettlementParticipant,
    SettlementReport,
    settle_legend_for,
    settle_standouts_only,
)
from world.stories.constants import StakeResolutionColumn
from world.stories.models import RiskCalibration, StakeOutcome

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Scene
    from world.societies.models import LegendSourceType
    from world.stories.models import StakeContractActivation

logger = logging.getLogger(__name__)


def held_fraction_for_activation(activation: StakeContractActivation) -> float:
    """Severity-weighted share of this contract's objectives that were held.

    Each ``Stake`` carries a ``severity``; the fraction is the summed severity
    of stakes resolved into the WIN column over the summed severity of every
    stake that resolved at all. So losing the town while beating the monsters
    pays for the monsters and not the town, weighted by how much each mattered.

    Unresolved stakes are excluded from both sides rather than counted as
    losses — a contract can be settled before every stake has an outcome, and
    treating "not yet decided" as "lost" would silently underpay.

    Returns 0.0 when nothing resolved, which settles to no shared deed.
    """
    outcomes = StakeOutcome.objects.filter(activation=activation).select_related("stake")
    total = 0
    held = 0
    for outcome in outcomes:
        severity = outcome.stake.severity
        total += severity
        if outcome.column == StakeResolutionColumn.WIN:
            held += severity
    if total <= 0:
        return 0.0
    return held / total


def authored_legend_award(effective_risk: str) -> int | None:
    """The staff-authored Legend award for this risk tier, if one is authored.

    ``RiskCalibration`` is already THE designer-tunable per-risk-tier config
    (severity bands, fuse hops, reward bands), so the Legend award for a tier
    belongs beside them rather than in a Python constant. Returns None when no
    row exists or the row leaves ``legend_award`` at 0, in which case the seam
    falls back to ``societies.constants.RISK_LEGEND_AWARDS``.

    0 means "not authored", not "this tier pays nothing" — a tier that should
    pay nothing is one below ``LEGEND_RISK_FLOOR``.
    """
    calibration = RiskCalibration.objects.filter(risk=effective_risk).first()
    if calibration is None or calibration.legend_award <= 0:
        return None
    return int(calibration.legend_award)


def participants_for_activation(
    activation: StakeContractActivation,
    sheets: Sequence[CharacterSheet],
) -> list[SettlementParticipant]:
    """Build settlement participants from the contract's contribution ledger.

    Each sheet contributes its class level (for station) and its best
    success_level across contributions that served a *crucial* objective (for
    the standout pass). A sheet that acted but never on anything crucial still
    settles for its share of the shared deed; it just cannot be a standout.
    """
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.societies.models import LegendContribution  # noqa: PLC0415

    best_crucial: dict[int, int] = {}
    contributions = LegendContribution.objects.filter(
        activation=activation,
        was_crucial=True,
    ).values_list("character_sheet_id", "success_level")
    for sheet_id, success_level in contributions:
        current = best_crucial.get(sheet_id)
        if current is None or success_level > current:
            best_crucial[sheet_id] = success_level

    participants: list[SettlementParticipant] = []
    for sheet in sheets:
        persona = active_persona_for_sheet(sheet)
        if persona is None:
            logger.info(
                "legend settlement: sheet %s has no active persona; skipping.",
                sheet.pk,
            )
            continue
        participants.append(
            SettlementParticipant(
                persona=persona,
                level=sheet.current_level,
                crucial_success_level=best_crucial.get(sheet.pk),
            )
        )
    return participants


def settle_legend_for_activation(  # noqa: PLR0913 - mirrors the seam it adapts
    activation: StakeContractActivation,
    *,
    sheets: Sequence[CharacterSheet],
    source_type: LegendSourceType,
    title: str,
    description: str = "",
    scene: Scene | None = None,
    concealed: bool = False,
) -> SettlementReport:
    """Settle Legend for a locked stakes contract.

    Routes to the shared-deed path when any objective was held, and to the
    standouts-only path when none was — because a lost unit still owes a song
    to whoever did something brilliant under pressure while it was being lost.
    """
    participants = participants_for_activation(activation, sheets)
    held = held_fraction_for_activation(activation)
    story = activation.beat.episode.chapter.story if activation.beat_id else None

    if held <= 0:
        return settle_standouts_only(
            effective_risk=activation.effective_risk,
            target_level=activation.declared_target_level,
            participants=participants,
            source_type=source_type,
            title=title,
            scene=scene,
            story=story,
        )
    return settle_legend_for(
        risk_award_override=authored_legend_award(activation.effective_risk),
        effective_risk=activation.effective_risk,
        target_level=activation.declared_target_level,
        held_fraction=held,
        participants=participants,
        source_type=source_type,
        title=title,
        description=description,
        scene=scene,
        story=story,
        concealed=concealed,
    )
