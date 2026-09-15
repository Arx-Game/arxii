"""Who is in a scene, read off its log (#3867, ADR-0300).

Where a character stands is presence (the room's contents). Whether they are in
the scene is participation, and participation begins with the first pose: a
character has *entered* a scene once the scene holds a room-heard line of theirs
(a pose, a say or an emit). Nothing is stored for it; the log is the fact. A
character present in the room without such a line stands at the *threshold*:
listed, able to see everything, not yet addressable, and about to make their
entrance with their first line.

``SceneParticipation`` is a different question (admin co-ownership and read
membership) and is deliberately not consulted here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.scenes.constants import InteractionMode, ScenePrivacyMode

if TYPE_CHECKING:
    from world.scenes.models import Scene

# The modes whose first line enters a scene. Whispers and mutters are directed
# and enter nothing; action and outcome rows are not a character's own line.
ENTRANCE_MODES: frozenset[str] = frozenset(
    {InteractionMode.POSE, InteractionMode.SAY, InteractionMode.EMIT}
)


def keeps_a_log(scene: Scene) -> bool:
    """Whether ``scene`` records its lines at all; an ephemeral scene has no entrances."""
    return scene.privacy_mode != ScenePrivacyMode.EPHEMERAL


def entered_sheet_ids(scene: Scene) -> set[int]:
    """The character sheets that have entered ``scene``, in one query.

    Built for the room-state payload, which marks every present character at once.
    """
    from world.scenes.models import Interaction  # noqa: PLC0415

    return set(
        Interaction.objects.filter(scene=scene, mode__in=ENTRANCE_MODES)
        .values_list("persona__character_sheet_id", flat=True)
        .distinct()
    )


def has_entered(scene: Scene, character_sheet_id: int) -> bool:
    """Whether the character behind ``character_sheet_id`` has entered ``scene``."""
    from world.scenes.models import Interaction  # noqa: PLC0415

    return Interaction.objects.filter(
        scene=scene,
        mode__in=ENTRANCE_MODES,
        persona__character_sheet_id=character_sheet_id,
    ).exists()
