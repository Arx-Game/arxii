"""How a mission prices the Legend it pays (#3463, ADR-0249; extracted #3468).

Legend is settled, not asserted: an authored number is a declared wager and the
payout is priced against what was actually at stake, for whom. A mission states
what was at stake in its template's ``risk_tier``, which
``risk_tier_to_renown_risk`` already maps onto the shared ``RenownRisk`` ladder
for the #2051 legend floor. **So a mission is its own settled context** — no
``StakeContractActivation`` is consulted, and none needs to be.

That is what makes the deferred POST_CRON payout tractable. A mission's stakes
contract has long closed by the time the cron runs; if the price depended on an
open activation there would be nothing left to read. It does not.

Both mission Legend paths share this: the terminal renown emission at
resolution time, and the queued ``LEGEND_POINTS`` grant at cron time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.missions.models import MissionTemplate


def mission_settlement_context(
    template: MissionTemplate, sheet: CharacterSheet
) -> tuple[str | None, int]:
    """This earner's PERSONAL risk on this mission, and their station.

    Two scales are in play and they are not the same one. ``risk_tier`` (1-5) is
    how dangerous the mission is; ``level_band_min``/``level_band_max`` are the
    CHARACTER LEVELS it is pitched at. The threat level is the band, not the
    tier — comparing a character's level to a 1-5 tier is apples to oranges,
    and an earlier pass at this (#3463) did exactly that.

    So:

    * **declared risk** is ``risk_tier_to_renown_risk(risk_tier)`` — what the
      mission claims to be worth, on the shared ``RenownRisk`` ladder that the
      #2051 legend floor already uses.
    * **threat level** is ``level_band_max`` — the top of the band the mission
      was written for.
    * **personal risk** prices that declaration against THIS earner's level
      through ``compute_effective_risk`` (ADR-0077), which is the same ladder
      shift every other source uses. A level-20 running a mission banded for
      level 4 decays below the floor and earns nothing, however lethal the
      mission is to the people it was written for. Personal risk is table
      stakes (ADR-0249).
    * **station** is ``min(earner level, threat level)``.

    Returns ``(None, 0)`` for a mission with no band or no tier, which prices
    to no Legend. ``CharacterSheet.current_level`` is 0 for a character with no
    class assignments, which also yields station 0 — correct for a classless NPC.
    """
    from world.missions.constants import risk_tier_to_renown_risk  # noqa: PLC0415
    from world.societies.legend_settlement import station_for  # noqa: PLC0415
    from world.stories.services.stakes import compute_effective_risk  # noqa: PLC0415

    tier = int(template.risk_tier or 0)
    threat_level = int(template.level_band_max or 0)
    if tier <= 0 or threat_level <= 0:
        return None, 0
    declared = risk_tier_to_renown_risk(tier)
    level = sheet.current_level
    personal_risk = compute_effective_risk(declared, threat_level, level)
    return personal_risk, station_for(level, threat_level)


def priced_legend_value(declared_amount: int, settled_risk: str | None, station: int) -> int:
    """What a mission Legend award actually pays.

    ``declared_amount`` is the author's number on the reward line — a ceiling,
    not a payout (ADR-0249). The tier's own award is the other ceiling, and
    Legend pays the **weaker** of the two. Below the floor, or with no station,
    it pays nothing at all: not a reduced award, zero.

    The returned value is UNTUNED by station. Station is stamped on the entry
    (``LegendEntry.earned_at_level``) and applied on read by the advancement
    gate, so retuning the multiplier never requires recomputing history.
    """
    from world.societies.constants import (  # noqa: PLC0415
        RISK_LEGEND_AWARDS,
        risk_meets_legend_floor,
    )

    if not settled_risk or station <= 0:
        return 0
    if not risk_meets_legend_floor(settled_risk):
        return 0
    tier_award = RISK_LEGEND_AWARDS.get(settled_risk, 0)
    if declared_amount <= 0:
        return tier_award
    return min(int(declared_amount), tier_award)
