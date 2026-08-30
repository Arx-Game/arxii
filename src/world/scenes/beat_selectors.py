"""Which story beat is a scene running right now (#3433, #3463).

The precedence chain lived inline in ``SceneDetailSerializer._resolve_declared_risk``
when #3433/#3461 added the scene-header risk badge. #3463 needs the *same*
resolution to decide which stakes contract a check contributes to — and a second
copy would drift, which matters more here than usual: the badge tells a player
"this is what you are risking", and settlement decides what they earned for it.
If those two ever disagreed, the game would be lying to someone.

So the chain lives here once, returns the ``Beat``, and both callers read it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.scenes.constants import DecisiveCheckMarkerStatus

if TYPE_CHECKING:
    from world.scenes.models import Scene
    from world.stories.models import Beat, StakeContractActivation


def running_beat_for_scene(scene: Scene | None) -> Beat | None:
    """The beat a scene is currently running, by declared precedence.

    ``scene.running_beat`` (#3425) wins; else the active (not-yet-completed)
    combat encounter's ``story_beat``; else the scene's PENDING
    ``DecisiveCheckMarker``'s beat; else None.

    Reads ``story_beat`` — never ``CombatEncounter.risk_level``, which is the
    combat ``RiskLevel`` enum driving the acknowledgement gate, a different
    field one hop away.
    """
    if scene is None:
        return None
    if scene.running_beat_id is not None:
        return scene.running_beat
    encounter = (
        scene.combat_encounters.filter(completed_at__isnull=True)
        .select_related("story_beat")
        .first()
    )
    if encounter is not None and encounter.story_beat_id is not None:
        return encounter.story_beat
    marker = (
        scene.decisive_markers.filter(status=DecisiveCheckMarkerStatus.PENDING)
        .select_related("beat")
        .first()
    )
    if marker is not None:
        return marker.beat
    return None


def open_activation_for_scene(scene: Scene | None) -> StakeContractActivation | None:
    """The open stakes contract a scene is playing under, if any.

    None when the scene runs no beat, or its beat has no locked contract — in
    which case nothing that happens here can earn Legend, because there is
    nothing at stake to price it against.
    """
    from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

    beat = running_beat_for_scene(scene)
    if beat is None:
        return None
    return get_open_activation(beat)
