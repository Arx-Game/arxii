"""Battle conclusion -> story beat auto-wiring (#1785).

Wires a concluded war-scale Battle into the same record_outcome_tier_completion
seam #1746 already proved out for CombatEncounter's ENCOUNTER_COMPLETED wiring:
classify_battle_conclusion_outcome maps Battle.outcome to a designer-tunable
CheckOutcome via BattleOutcomeMapping, and resolve_battle_beats resolves any
linked OUTCOME_TIER beat.

Unlike combat's wiring, this is a direct function call from conclude_battle,
not a flow event/TriggerDefinition — Battle has no location (#1733), so the
location-based flows.emit_event machinery doesn't apply, and conclude_battle
is already the single call-site choke point (#1785 spec Decision 1).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.battles.constants import BattleParticipantStatus
from world.traits.models import CheckOutcome

if TYPE_CHECKING:
    from world.battles.models import Battle

logger = logging.getLogger(__name__)


def classify_battle_conclusion_outcome(battle: Battle) -> CheckOutcome | None:
    """Map a concluded battle's outcome to a CheckOutcome tier.

    Returns the designer-authored CheckOutcome for battle.outcome, or None
    when no mapping row exists or the row's check_outcome is null. None
    signals the caller to resolve the beat to PENDING_GM_REVIEW rather than
    firing a consequence pool.

    Args:
        battle: A concluded Battle. Its ``outcome`` drives the mapping lookup.

    Returns:
        The mapped CheckOutcome, or None.

    Raises:
        ValueError: if the battle has no outcome set (programmer error — only
            called post-conclusion, from resolve_battle_beats).
    """
    from world.battles.constants import BattleOutcome  # noqa: PLC0415
    from world.battles.models import BattleOutcomeMapping  # noqa: PLC0415

    if not battle.outcome or battle.outcome == BattleOutcome.UNRESOLVED:
        msg = (
            f"Battle {battle.pk} has no outcome; classify_battle_conclusion_outcome "
            "should only be called on a concluded battle."
        )
        raise ValueError(msg)

    mapping = BattleOutcomeMapping.objects.filter(outcome=battle.outcome).first()
    return mapping.check_outcome if mapping is not None else None


def activate_stakes_for_battle(battle: Battle) -> None:
    """Lock any staked beats' contracts for this battle's enlisted party.

    Called from begin_battle_round when opening the battle's very first round
    (#1785 spec Decision 3). Collects every currently-ACTIVE participant's
    character sheet; no-ops when there are none. For each staked UNSATISFIED
    beat linked to the battle's scene, boundary-screens it (same guard as
    combat's activate_stakes_for_scene) and activates it with
    scale_by_party_level=False — a war's stakes reflect the objective, not
    which specific PCs happen to be enlisted (#1785 spec Decision 4; ADR-0080).
    """
    from world.stories.services.boundaries import check_stake_boundaries  # noqa: PLC0415
    from world.stories.services.stakes import (  # noqa: PLC0415
        activate_stakes_contract,
        staked_unsatisfied_beats_for_scene,
    )

    sheets = [
        p.character_sheet for p in battle.participants.filter(status=BattleParticipantStatus.ACTIVE)
    ]
    if not sheets:
        return
    for beat in staked_unsatisfied_beats_for_scene(battle.scene):
        report = check_stake_boundaries(beat.stakes.all(), sheets)
        if not report.cleared:
            logger.info(
                "Stakes contract on battle beat %s not activated: blocked or "
                "awaiting sign-off on a player boundary.",
                beat.pk,
            )
            continue
        activate_stakes_contract(beat, sheets, scale_by_party_level=False)


def resolve_battle_beats(battle: Battle) -> None:
    """Resolve every UNSATISFIED OUTCOME_TIER beat linked to a concluded battle.

    Called directly from conclude_battle (#1785 spec Decision 1 — no event or
    trigger; Battle has no location, so flows.emit_event doesn't apply, and
    conclude_battle is already the single call-site choke point). One Battle
    grades as one outcome tier, applied to every linked beat (#1785 spec
    Decision 2) — per-front independent grading is #1760's job.

    No withdrawal path: BattleOutcome has no FLED/ABANDONED-equivalent value —
    a timed-out battle still grades a decisive/marginal winner via
    maybe_conclude_on_timer.
    """
    from world.stories.constants import BeatOutcome, BeatPredicateType  # noqa: PLC0415
    from world.stories.models import Beat, EpisodeScene  # noqa: PLC0415
    from world.stories.services.beats import record_outcome_tier_completion  # noqa: PLC0415
    from world.stories.services.progress import (  # noqa: PLC0415
        get_active_progress_for_story,
    )

    scene = battle.scene
    episode_ids = EpisodeScene.objects.filter(scene=scene).values_list("episode_id", flat=True)
    beats = list(
        Beat.objects.filter(
            episode_id__in=episode_ids,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
    )
    if not beats:
        return

    outcome_tier = classify_battle_conclusion_outcome(battle)

    for beat in beats:
        progress = get_active_progress_for_story(beat.episode.chapter.story)
        if progress is None:
            logger.debug(
                "Battle conclusion: beat %s — no active progress for story; skipping.",
                beat.pk,
            )
            continue
        if outcome_tier is None:
            record_outcome_tier_completion(
                progress=progress,
                beat=beat,
                force_outcome=BeatOutcome.PENDING_GM_REVIEW,
            )
        else:
            record_outcome_tier_completion(
                progress=progress,
                beat=beat,
                outcome_tier=outcome_tier,
            )
