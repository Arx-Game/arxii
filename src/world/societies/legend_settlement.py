"""Legend settlement: the one seam that prices a deed (#3463).

**Would bards make songs about this?** That is the whole question this module
answers, and it answers it once, at the *end* of a story unit, from a record of
what each character did across it — never at the moment of an individual act.

Before #3463 twelve sites minted Legend directly at flat authored values, and ten
of them never asked whether anything was at stake or whether it accomplished
anything. Draining a helpless victim minted a deed; picking a lock minted a deed;
a beat completed without ever locking its stakes contract paid its full authored
tier. This module replaces all of that with one priced settlement.

The rules it enforces, in order:

1. **Peril floor, applied PER PERSON.** Risk is priced against each earner's
   own level, not the party's average, and must reach ``LEGEND_RISK_FLOOR`` for
   *that person* before they earn anything. Below it, they mint nothing — not a
   reduced award, zero. "We basically need all legend rewards to go through a
   filter that determines their personal degree of risk; if they had very
   little, it should be essentially zero" (Tehom, 2026-08-30). A level-10 hero
   who obliterates a company of level-1 mooks was never in danger, and the
   fact that the mooks were lethal to everyone else does not make it a song
   about them. Personal risk is table stakes.
2. **Outcome.** The shared deed pays on the severity-weighted share of objectives
   actually held. Beat the monsters but let the town burn and you are paid for
   the monsters, not the town.
3. **Station.** Each participant's deed is *stamped* with
   ``min(their class level, the threat's level)``. The stamp is not applied to
   the stored value: a deed's worth as a story does not depend on who did it,
   and the level-1 and the level-5 who both survived the same level-5 threat
   did the equally impressive thing. What station governs is how much the deed
   advances *you*, which the advancement gate derives on read
   (``LegendRequirement.is_met_by_character``). Storing the value untuned means
   retuning the multiplier never requires recomputing a single historical row.
4. **Standouts.** A crucial contribution resolved brilliantly pays its actor a
   solo deed *even when the unit was lost* — generalizing ADR-0122's battle-only
   standout pass, whose own words were "a losing-side rescue is still a story
   worth telling".

**Dependency direction (ADR-0010).** ``societies`` is the reusable primitive
here; ``stories``, ``battles`` and ``missions`` are its consumers. So this module
takes system-agnostic inputs — an effective risk, a target level, a held
fraction, participants with levels — and each consumer adapts its own world into
that shape. ``world.stories.services.legend_settlement`` is the stakes-contract
adapter. This module imports none of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING

from world.societies.constants import (
    LEGEND_RISK_FLOOR,
    RISK_LEGEND_AWARDS,
    risk_meets_legend_floor,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.scenes.models import Persona, Scene
    from world.societies.models import LegendEntry, LegendEvent, LegendSourceType
    from world.stories.models import Story

logger = logging.getLogger(__name__)

# FALLBACK defaults only. The authored values live on the
# LegendSettlementConfig singleton (#3463) — per Tehom's ruling, every number
# here is a lookup table first and a constant only when no table is defined.
# These are what the singleton is created with, and what a failed config read
# falls back to so a settlement can never be broken by a missing tuning row.
#
# STANDOUT_FRACTION: share of a participant's take that a standout pays its
# actor on a LOST unit. Deliberately small — brilliance in defeat is "much
# less", a consolation rather than a second full award.
# STANDOUT_SUCCESS_LEVEL: mirrors battles' bar (ADR-0122), clearly above bare
# success.
STANDOUT_FRACTION = 0.2
STANDOUT_SUCCESS_LEVEL = 2


def _standout_dials() -> tuple[float, int]:
    """Authored (fraction, min success level), falling back to the constants."""
    from django.db import OperationalError, ProgrammingError  # noqa: PLC0415

    from world.societies.models import LegendSettlementConfig  # noqa: PLC0415

    try:
        config = LegendSettlementConfig.get_active_config()
    except (ProgrammingError, OperationalError):
        # Table not yet created (mid-migrate / fresh DB). Narrowly these two —
        # any other failure is a real fault and should surface.
        return STANDOUT_FRACTION, STANDOUT_SUCCESS_LEVEL
    return (
        config.standout_fraction_tenths / 10,
        int(config.standout_min_success_level),
    )


@dataclass(frozen=True)
class SettlementParticipant:
    """One character present for a settled unit.

    ``level`` is their class level at settlement; ``crucial_success_level`` is
    their best success_level on a contribution that served a crucial objective,
    or None when they made no crucial contribution.
    """

    persona: Persona
    level: int
    crucial_success_level: int | None = None
    #: An authored title for this participant's standout deed, when the source
    #: has a better name for it than the generic one. Battles curate these per
    #: dramatic action kind ("Daring rescue at X") and a name is the whole point
    #: of a legendary deed, so the seam carries it rather than flattening every
    #: standout to one string.
    standout_title: str | None = None
    #: This character's OWN effective risk, priced against their level rather
    #: than the party's average (#3463). A level-10 standing in a fight pitched
    #: at level 5 was not personally in danger, and earns nothing for it however
    #: real the danger was to everyone else. Consumers compute this; societies
    #: must not import the stories-side pricing (ADR-0010). None falls back to
    #: the contract-wide risk, which is the pre-personal-filter behaviour.
    personal_risk: str | None = None


@dataclass(frozen=True)
class SettlementReport:
    """What settlement did, and — when it did nothing — why.

    ``reason`` is always populated, including on success, because "why did this
    pay nothing" is the question staff will actually ask of this system.
    """

    minted: bool
    reason: str
    event: LegendEvent | None = None
    entries: list[LegendEntry] = field(default_factory=list)
    standouts: list[LegendEntry] = field(default_factory=list)


def station_for(participant_level: int, target_level: int) -> int:
    """The lower of what you are and what you faced (#3463 decision 8).

    A level 1 beating a level 2 settles at station 1; a level 2 beating that
    same level 2 settles at station 2 and is paid more for it. A level 2
    beating a level 1 settles at station 1 — the same as the level 1 who beat
    it, which is exactly the point: slumming is inconsequential.
    """
    return max(0, min(participant_level, target_level))


def station_multiplier(station: int) -> int:
    """How much a deed won at ``station`` counts toward advancement.

    Linear in station today: a deed won at station 5 advances you five times as
    far as one won at station 1. Deliberately a code constant rather than an
    authored row — this is not a tuning knob but the rule that you cannot bank
    above your station or by slumming, and authoring it would let that rule be
    edited away. Tuning it is a deploy, and costs nothing retroactively because
    ``LegendEntry.base_value`` is stored UNTUNED and this is applied on read.
    """
    return max(0, station)


def settle_legend_for(  # noqa: PLR0913 - one seam, and every input is load-bearing
    *,
    effective_risk: str,
    target_level: int,
    held_fraction: float,
    participants: Sequence[SettlementParticipant],
    source_type: LegendSourceType,
    title: str,
    description: str = "",
    scene: Scene | None = None,
    story: Story | None = None,
    concealed: bool = False,
    structurally_perilous: bool = False,
    risk_award_override: int | None = None,
) -> SettlementReport:
    """Price and mint the Legend a settled unit earned. The only mint seam.

    Args:
        effective_risk: The unit's level-priced risk. NOT the authored
            declaration — see ADR-0249; a declared value passed here would
            reopen the exact hole this module closes.
        target_level: The threat's level, for station.
        held_fraction: Severity-weighted share of objectives held, 0.0-1.0.
        participants: Who was there, at what level, with their best crucial
            contribution.
        risk_award_override: The authored ``RiskCalibration.legend_award`` for
            this tier, when a calibration row exists. ``RISK_LEGEND_AWARDS`` is
            only the fallback — societies must not import stories (ADR-0010),
            so the consumer resolves the authored value and passes it in.
        structurally_perilous: Bypasses the floor for a source whose peril is
            intrinsic rather than declared. **Audere Majora only** — a crossing
            is always a legendary reward and cannot happen without great
            personal risk (Tehom, 2026-08-29). This is not a general waiver
            flag: it exists so one structurally-guaranteed source does not have
            to fake a stakes contract, and nothing authored can set it.

    Returns:
        A ``SettlementReport``; ``minted`` is False with a stated reason
        whenever the unit earned nothing.
    """
    if not participants:
        return SettlementReport(minted=False, reason="no participants resolved for the unit")

    if held_fraction <= 0:
        return SettlementReport(
            minted=False,
            reason="no objective was held; the shared deed pays nothing",
        )

    # The peril floor is a PER-PERSON filter (#3463). Everyone who was not
    # personally in danger drops out here, however dangerous the unit was to
    # the rest of the party.
    stations: dict[int, int] = {}
    for participant in participants:
        risk = participant.personal_risk or effective_risk
        if not structurally_perilous and not risk_meets_legend_floor(risk):
            continue
        station = station_for(participant.level, target_level)
        if station > 0:
            stations[participant.persona.pk] = station

    paid = [p for p in participants if p.persona.pk in stations]
    if not paid:
        return SettlementReport(
            minted=False,
            reason=(
                f"nobody was personally at risk: every participant priced below "
                f"the Legend floor {LEGEND_RISK_FLOOR!r}, or had no station"
            ),
        )

    risk_award = risk_award_override or RISK_LEGEND_AWARDS.get(effective_risk, 0)
    if structurally_perilous and risk_award <= 0:
        risk_award = RISK_LEGEND_AWARDS[LEGEND_RISK_FLOOR]

    # UNTUNED: the tale's worth, identical for everyone who was there. Station
    # is a per-participant stamp, never folded into the stored number.
    base_value = round(risk_award * held_fraction)
    if base_value <= 0:
        return SettlementReport(
            minted=False,
            reason="the priced award rounded to zero",
        )
    if not paid:
        return SettlementReport(
            minted=False,
            reason="every participant priced to zero (no station, or nothing held)",
        )

    from world.societies.services import create_legend_event  # noqa: PLC0415

    event, entries = create_legend_event(
        title[:200],
        source_type,
        base_value,
        [p.persona for p in paid],
        description=description,
        scene=scene,
        story=story,
        concealed=concealed,
        stations_by_persona=stations,
    )
    standouts = _mint_standouts(
        participants=participants,
        risk_award=risk_award,
        target_level=target_level,
        source_type=source_type,
        title=title,
        scene=scene,
        story=story,
        already_paid={p.persona.pk for p in paid},
    )
    return SettlementReport(
        minted=True,
        reason=(
            f"settled at effective risk {effective_risk!r}, "
            f"{held_fraction:.0%} of objectives held, {len(entries)} participant(s)"
        ),
        event=event,
        entries=list(entries),
        standouts=standouts,
    )


def settle_standouts_only(  # noqa: PLR0913 - mirrors settle_legend_for's inputs
    *,
    effective_risk: str,
    target_level: int,
    participants: Sequence[SettlementParticipant],
    source_type: LegendSourceType,
    title: str,
    scene: Scene | None = None,
    story: Story | None = None,
) -> SettlementReport:
    """The unit was lost, but brilliance under pressure is still worth a song.

    Generalizes ADR-0122's standout pass past ``Battle``. The shared deed pays
    nothing (no objective held), yet a crucial action resolved brilliantly still
    mints its actor a much smaller solo deed. The peril floor still applies —
    a spectacular lockpick with nothing at stake is not a song.
    """
    at_risk = [
        p for p in participants if risk_meets_legend_floor(p.personal_risk or effective_risk)
    ]
    if not at_risk:
        return SettlementReport(
            minted=False,
            reason="nobody was personally at risk; a lost unit still owes no song",
        )
    standouts = _mint_standouts(
        participants=at_risk,
        risk_award=RISK_LEGEND_AWARDS.get(effective_risk, 0),
        target_level=target_level,
        source_type=source_type,
        title=title,
        scene=scene,
        story=story,
        already_paid=set(),
    )
    return SettlementReport(
        minted=bool(standouts),
        reason=(
            f"{len(standouts)} standout contribution(s) paid on a lost unit"
            if standouts
            else "no contribution cleared the standout bar"
        ),
        standouts=standouts,
    )


def _mint_standouts(  # noqa: PLR0913 - mirrors settle_legend_for's inputs
    *,
    participants: Sequence[SettlementParticipant],
    risk_award: int,
    target_level: int,
    source_type: LegendSourceType,
    title: str,
    scene: Scene | None,
    story: Story | None,
    already_paid: set[int],
) -> list[LegendEntry]:
    """Solo deeds for crucial contributions resolved brilliantly.

    ``already_paid`` holds personas who took a share of the shared deed. They
    are skipped deliberately: on a *won* unit the shared deed is the reward, and
    stacking a standout on top would double-pay the same act. On a lost unit the
    set is empty, so every standout pays — which is the consolation case.
    """
    from world.societies.services import create_solo_deed  # noqa: PLC0415

    fraction, min_success_level = _standout_dials()
    minted: list[LegendEntry] = []
    for participant in participants:
        if participant.persona.pk in already_paid:
            continue
        # Same per-person peril filter as the shared deed: brilliance is only a
        # song when the person performing it was themselves at risk. A
        # untouchable hero's flourish on a battlefield that could not hurt them
        # is not a consolation deed.
        if participant.personal_risk is not None and not risk_meets_legend_floor(
            participant.personal_risk
        ):
            continue
        level = participant.crucial_success_level
        if level is None or level < min_success_level:
            continue
        station = station_for(participant.level, target_level)
        if station <= 0:
            continue
        value = round(risk_award * fraction)
        if value <= 0:
            continue
        deed_title = participant.standout_title or f"{title}: a deed remembered"
        entry = create_solo_deed(
            participant.persona,
            deed_title[:200],
            source_type,
            value,
            scene=scene,
            story=story,
            earned_at_level=station,
        )
        if entry is not None:
            minted.append(entry)
    return minted
