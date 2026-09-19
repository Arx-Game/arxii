"""Objective-first encounter read models (#3916).

Encounters already have two objective routing primitives: a story beat's stakes
contract and a scenario ENCOUNTER option.  This module only reads those rows. It
does not classify combat or introduce an objective model.  In particular, a
clock is a time signal and an encounter outcome is a fight signal; neither is
silently converted into the other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter


def _clock_payload(beat: Any, scene: Any) -> dict[str, Any] | None:
    """Return the scene clock for ``beat`` without exposing beat internals."""
    if beat is None or scene is None:
        return None
    from world.scenes.models import SceneClock  # noqa: PLC0415

    clock = SceneClock.objects.filter(scene=scene, beat=beat).order_by("-pk").first()
    if clock is None:
        return None
    return {
        "size": clock.size,
        "filled": clock.filled,
        "closed_reason": clock.closed_reason or None,
        "complete": clock.filled >= clock.size,
    }


def _scenario_snapshot(encounter: CombatEncounter) -> dict[str, Any]:
    """Read the objective and selected route for a scenario encounter."""
    deed = encounter.scenario_deed
    option = deed.option
    node = deed.node
    branches = []
    if deed.outcome_id is not None:
        route = option.routes.filter(outcome_tier_id=deed.outcome_id).order_by("pk").first()
        if route is not None:
            branches.append(
                {
                    "key": option.key,
                    "outcome": deed.outcome.name,
                    "column": None,
                    "label": route.outcome_text,
                }
            )
    return {
        "key": option.key,
        "source": "scenario",
        "label": option.authored_ic_framing or node.flavor_text,
        "clock": _clock_payload(deed.instance.source_beat, encounter.scene),
        "branches": branches,
    }


def _beat_for_encounter(encounter: CombatEncounter) -> Any:
    """Find the one beat the existing completion wiring may grade."""
    beat = encounter.story_beat
    if beat is not None:
        return beat
    from world.stories.constants import BeatKind  # noqa: PLC0415

    running = encounter.scene.running_beat
    if running is not None and running.kind == BeatKind.ENCOUNTER:
        return running
    return None


def _stake_branch_snapshots(beat: Any) -> list[dict[str, Any]]:
    """Return every authored branch selected by the stakes contract."""
    from world.stories.models import StakeOutcome  # noqa: PLC0415

    outcomes = (
        StakeOutcome.objects.filter(stake__beat=beat).select_related("resolution").order_by("pk")
    )
    branches = []
    for outcome in outcomes:
        resolution = outcome.resolution
        branches.append(
            {
                "key": (
                    resolution.outcome_key
                    if resolution and resolution.outcome_key
                    else outcome.column
                ),
                "column": outcome.column,
                "label": resolution.narrative_summary if resolution else "",
            }
        )
    return branches


def objective_snapshot(encounter: CombatEncounter) -> dict[str, Any] | None:
    """Build a safe active-objective/branch payload for encounter readers.

    The payload is derived from the existing scenario deed, beat, stakes, and
    scene clock rows.  ``branch`` is null until a route or stake outcome has
    actually been selected.  A FLED encounter therefore reports its authored
    scenario/withdrawal branch rather than being rewritten as a victory.
    """
    if encounter.scenario_deed_id is not None:
        return _scenario_snapshot(encounter)
    beat = _beat_for_encounter(encounter)
    if beat is None:
        return None
    branches = _stake_branch_snapshots(beat)
    if not branches:
        from world.stories.models import BeatCompletion  # noqa: PLC0415

        completion = (
            BeatCompletion.objects.filter(beat=beat).order_by("-recorded_at", "-pk").first()
        )
        if completion is not None:
            branches = [
                {
                    "key": completion.outcome,
                    "column": None,
                    "label": beat.player_resolution_text,
                }
            ]
    return {
        "key": f"beat:{beat.pk}",
        "source": "stakes",
        "label": beat.player_hint,
        "clock": _clock_payload(beat, encounter.scene),
        "branches": branches,
    }
