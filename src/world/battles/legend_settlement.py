"""Battle-side adapter for Legend settlement (#3467).

``world.societies.legend_settlement`` owns the rule — per-person peril floor,
held-objective share, station, standouts — and knows nothing about battles, so
``societies`` stays the reusable primitive every system points at (ADR-0010).
This module turns a concluded ``Battle`` into that seam's system-agnostic
inputs. ``world.stories.services.legend_settlement`` is the sibling for scene
stakes; ``world.missions.services.legend_pricing`` for missions.

**ADR-0080 is preserved, not contradicted.** That ADR keeps a war's *stakes*
un-scaled by who turned up: a bridge is worth the same whether militia or
legends fight over it, so ``activate_stakes_for_battle`` passes
``scale_by_party_level=False``. That governs what the **objective** is worth.
An individual's **Legend** is a different question — a demigod on that field
still risked nothing personally — so ``personal_risk`` prices the beat's
*declared* risk against each earner's own level. The two rules answer different
questions and hold simultaneously.

**ADR-0122's curation survives.** A battle standout is specifically a
RESCUE/ROUT/BREACH resolved at or above ``STANDOUT_SUCCESS_LEVEL``, on either
side — not any high roll. Battles already record that in
``BattleActionDeclaration``, at a better grain than the generic
``LegendContribution`` ledger, so this reads that rather than adding a third
record of the same thing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.battles.constants import DRAMATIC_KINDS, STANDOUT_SUCCESS_LEVEL
from world.battles.models import BattleActionDeclaration
from world.societies.legend_settlement import (
    SettlementParticipant,
    SettlementReport,
    settle_legend_for,
    settle_standouts_only,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.battles.models import Battle
    from world.character_sheets.models import CharacterSheet
    from world.societies.models import LegendSourceType
    from world.stories.models import StakeContractActivation

logger = logging.getLogger(__name__)


def activation_for_battle(battle: Battle) -> StakeContractActivation | None:
    """The stakes contract this battle was fought under, if any.

    ``activate_stakes_for_battle`` locks a contract per staked beat linked to
    the battle's scene when the first round opens. ``None`` for an ad-hoc
    battle with no staked beat — which advances nobody, the same rule as
    everywhere: no declared target level, no station.
    """
    from world.stories.models import StakeContractActivation  # noqa: PLC0415

    if battle.scene_id is None:
        return None
    return (
        StakeContractActivation.objects.filter(beat__episode__episode_scenes__scene=battle.scene)
        .order_by("-locked_at")
        .first()
    )


def participants_for_battle(
    battle: Battle,
    sheets: Sequence[CharacterSheet],
    activation: StakeContractActivation,
) -> list[SettlementParticipant]:
    """Build settlement participants from the battle's own action record.

    ``crucial_success_level`` comes from each sheet's best DRAMATIC-kind
    declaration at or above the standout bar — ADR-0122's curation, kept
    deliberately rather than accepting any high roll.

    ``personal_risk`` prices the beat's DECLARED risk against this earner's
    level. Declared, not the activation's effective value, precisely because
    ADR-0080 skipped party scaling there: the war's tier is the honest input,
    and the personal filter is applied per earner on top of it.
    """
    from world.battles.legend_wiring import STANDOUT_TITLES  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.stories.services.stakes import compute_effective_risk  # noqa: PLC0415

    best_dramatic: dict[int, int] = {}
    titles: dict[int, str] = {}
    declarations = BattleActionDeclaration.objects.filter(
        participant__battle=battle,
        resolved=True,
        success_level__gte=STANDOUT_SUCCESS_LEVEL,
        action_kind__in=DRAMATIC_KINDS,
    ).values_list("participant__character_sheet_id", "success_level", "action_kind")
    for sheet_id, success_level, action_kind in declarations:
        current = best_dramatic.get(sheet_id)
        if current is None or success_level > current:
            best_dramatic[sheet_id] = success_level
            # The curated per-kind name travels with the deed. "Daring rescue at
            # Siege of the Salt Marsh" is a better tale than a generic string,
            # and a deed's NAME is what makes it a song.
            titles[sheet_id] = STANDOUT_TITLES[action_kind].format(battle=battle.name)

    target_level = activation.declared_target_level
    participants: list[SettlementParticipant] = []
    for sheet in sheets:
        persona = active_persona_for_sheet(sheet)
        if persona is None:
            logger.info("battle settlement: sheet %s has no active persona; skipping.", sheet.pk)
            continue
        participants.append(
            SettlementParticipant(
                persona=persona,
                level=sheet.current_level,
                crucial_success_level=best_dramatic.get(sheet.pk),
                standout_title=titles.get(sheet.pk),
                personal_risk=compute_effective_risk(
                    activation.declared_risk, target_level, sheet.current_level
                ),
            )
        )
    return participants


def settle_legend_for_battle(
    battle: Battle,
    *,
    winning_sheets: Sequence[CharacterSheet],
    standout_sheets: Sequence[CharacterSheet],
    source_type: LegendSourceType,
) -> SettlementReport:
    """Settle a concluded battle's Legend.

    Won battles pay the winning side a shared deed plus any standouts; a lost
    one still pays standouts on either side, which is ADR-0122's original point
    and is now the general rule (ADR-0249).
    """
    from world.stories.services.legend_settlement import (  # noqa: PLC0415
        authored_legend_award,
        held_fraction_for_activation,
    )

    activation = activation_for_battle(battle)
    if activation is None:
        logger.info(
            "Battle %s concluded with no staked beat — no station, so no Legend. "
            "An ad-hoc battle advances nobody.",
            battle.pk,
        )
        return SettlementReport(minted=False, reason="battle has no staked beat")

    held = held_fraction_for_activation(activation)
    story = battle.campaign_story
    standouts = participants_for_battle(battle, standout_sheets, activation)

    if held <= 0 or not winning_sheets:
        return settle_standouts_only(
            effective_risk=activation.declared_risk,
            target_level=activation.declared_target_level,
            participants=standouts,
            source_type=source_type,
            title=f"At {battle.name}",
            scene=battle.scene,
            story=story,
        )

    report = settle_legend_for(
        risk_award_override=authored_legend_award(activation.declared_risk),
        effective_risk=activation.declared_risk,
        target_level=activation.declared_target_level,
        held_fraction=held,
        participants=participants_for_battle(battle, winning_sheets, activation),
        source_type=source_type,
        title=f"Victory at {battle.name}",
        scene=battle.scene,
        story=story,
    )

    # ADR-0122: standout deeds STACK with the victory event, "by design" — a
    # shared deed says *we won this together*, a standout says *and this person
    # did something extraordinary*. Different claims about different things.
    #
    # The generic seam disagrees: settle_legend_for's standout pass skips
    # anyone who already took a share, on the reasoning that stacking
    # double-pays the same act (#3463). That reasoning holds for a scene where
    # the "crucial contribution" IS the thing the shared deed is paying for; it
    # does not hold for a war, where a rescue under fire is not what the
    # victory deed was about. So battles run the standout pass separately over
    # every standout sheet, winners included, preserving ADR-0122.
    #
    # Flagged rather than silently divergent: whether the generic seam should
    # also stack is a live design question, not settled here.
    standout_report = settle_standouts_only(
        effective_risk=activation.declared_risk,
        target_level=activation.declared_target_level,
        participants=standouts,
        source_type=source_type,
        title=f"At {battle.name}",
        scene=battle.scene,
        story=story,
    )
    return SettlementReport(
        minted=report.minted or standout_report.minted,
        reason=f"{report.reason}; standouts: {standout_report.reason}",
        event=report.event,
        entries=report.entries,
        standouts=[*report.standouts, *standout_report.standouts],
    )
