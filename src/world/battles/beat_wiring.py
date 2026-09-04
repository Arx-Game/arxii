"""Battle conclusion -> story beat auto-wiring (#1785).

Wires a concluded war-scale Battle into the same record_outcome_tier_completion
seam #1746 already proved out for CombatEncounter's ENCOUNTER_COMPLETED wiring:
beat_for_scene_conclusion (#3559) picks the single beat a concluded battle may
grade - the battle's own explicitly routed story_beat, or the battle scene's
running beat when it is itself the objective (kind ENCOUNTER) -
classify_battle_conclusion_outcome maps Battle.outcome to a designer-tunable
CheckOutcome via BattleOutcomeMapping, and resolve_battle_beats resolves it.

Unlike combat's wiring, this is a direct function call from conclude_battle,
not a flow event/TriggerDefinition — Battle has no location (#1733), so the
location-based flows.emit_event machinery doesn't apply, and conclude_battle
is already the single call-site choke point (#1785 spec Decision 1).

activate_stakes_for_battle (called from begin_battle_round's round 1) scopes
to battle.story_beat alone when that beat is itself staked and unsatisfied
(#3569, session-prep pre-staging) rather than every staked beat sharing the
battle's scene -- a pre-staged battle's own routed beat is the only one this
specific battle should be able to lock.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.battles.constants import BattleParticipantStatus
from world.societies.constants import RenownRisk
from world.traits.models import CheckOutcome

if TYPE_CHECKING:
    from world.battles.models import Battle

logger = logging.getLogger(__name__)


def classify_battle_conclusion_outcome(battle: Battle) -> CheckOutcome:
    """Map a concluded battle's outcome to a CheckOutcome tier.

    Args:
        battle: A concluded Battle. Its ``outcome`` drives the mapping lookup.

    Returns:
        The designer-authored CheckOutcome for battle.outcome.

    Raises:
        ValueError: if the battle has no outcome set (programmer error - only
            called post-conclusion, from resolve_battle_beats).
        BattleOutcomeMapping.DoesNotExist: no row is authored for this
            outcome. Missing content, not a data flag the caller branches on
            - see resolve_battle_beats.
    """
    from world.battles.constants import BattleOutcome  # noqa: PLC0415
    from world.battles.models import BattleOutcomeMapping  # noqa: PLC0415

    if not battle.outcome or battle.outcome == BattleOutcome.UNRESOLVED:
        msg = (
            f"Battle {battle.pk} has no outcome; classify_battle_conclusion_outcome "
            "should only be called on a concluded battle."
        )
        raise ValueError(msg)

    mapping = BattleOutcomeMapping.objects.get(outcome=battle.outcome)
    return mapping.check_outcome


def activate_stakes_for_battle(battle: Battle) -> None:
    """Lock any staked beats' contracts for this battle's enlisted party.

    Called from begin_battle_round when opening the battle's very first round
    (#1785 spec Decision 3). Collects every currently-ACTIVE participant's
    character sheet; no-ops when there are none. When ``battle.story_beat``
    is set and is itself a staked, still-UNSATISFIED beat, activation is
    scoped to that one beat only (#3569) -- a battle explicitly routed to a
    beat via session-prep pre-staging must not also lock a sibling staked
    beat that merely shares the battle's scene. Otherwise falls back to the
    pre-#3569 rule: every staked UNSATISFIED beat linked to the battle's
    scene. Each candidate beat is boundary-screened (same guard as combat's
    activate_stakes_for_scene) and activated with scale_by_party_level=False
    -- a war's stakes reflect the objective, not which specific PCs happen to
    be enlisted (#1785 spec Decision 4; ADR-0080).
    """
    from world.stories.constants import BeatOutcome  # noqa: PLC0415
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

    routed_beat = battle.story_beat
    if (
        routed_beat is not None
        and routed_beat.outcome == BeatOutcome.UNSATISFIED
        and routed_beat.risk != RenownRisk.NONE
    ):
        beats = [routed_beat]
    else:
        beats = staked_unsatisfied_beats_for_scene(battle.scene)

    for beat in beats:
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
    """Resolve the one beat linked to a concluded battle (#3559).

    Called directly from conclude_battle (#1785 spec Decision 1 - no event or
    trigger; Battle has no location, so flows.emit_event doesn't apply, and
    conclude_battle is already the single call-site choke point).
    beat_for_scene_conclusion picks at most one beat - the battle's own
    explicitly routed story_beat, or the battle scene's running beat when it
    is itself the objective (kind ENCOUNTER); per-front independent grading
    stays #1760's job, not this wiring's.

    No withdrawal path: BattleOutcome has no FLED/ABANDONED-equivalent value -
    a timed-out battle still grades a decisive/marginal winner via
    maybe_conclude_on_timer. A missing BattleOutcomeMapping row is content,
    not a pause - it is logged as an error (surfaced on the admin sentinel,
    #3444) and the beat is left open.
    """
    from world.battles.models import BattleOutcomeMapping  # noqa: PLC0415
    from world.stories.services.beats import (  # noqa: PLC0415
        beat_for_scene_conclusion,
        record_outcome_tier_completion,
    )
    from world.stories.services.progress import (  # noqa: PLC0415
        get_active_progress_for_story,
    )

    beat = beat_for_scene_conclusion(battle.scene, battle.story_beat)
    if beat is None:
        return

    progress = get_active_progress_for_story(beat.episode.chapter.story)
    if progress is None:
        logger.debug(
            "Battle conclusion: beat %s - no active progress for story; skipping.",
            beat.pk,
        )
        return

    try:
        tier = classify_battle_conclusion_outcome(battle)
    except BattleOutcomeMapping.DoesNotExist:
        logger.exception(
            "No BattleOutcomeMapping for outcome=%s; beat %s left open "
            "(required content, see the admin sentinel).",
            battle.outcome,
            beat.pk,
        )
        return

    record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=tier)
